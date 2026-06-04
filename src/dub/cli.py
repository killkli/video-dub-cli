from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import click
import yaml

from dub.config import load_config
from dub.errors import UserError
from dub.runtime_paths import pipeline_scripts_dir
from dub.project import STAGE_DIRS, create_project, initialize_project, project_input_info
from dub.runner import run_pipeline
from dub.state import load_state, new_state, save_state
from dub.tts_engines import builtin_backends
from dub.tts_engines.omnivoice import readiness as omnivoice_readiness
from dub.tts_engines.voxcpme import readiness as voxcpme_readiness


def _prepare_project(video: Path, project_dir: str | None, cfg) -> Path:
    if project_dir:
        pdir = Path(project_dir)
        if pdir.exists() and (pdir / ".dub" / "state.json").exists():
            return pdir
        return initialize_project(pdir, video)
    return create_project(cfg.paths.dub_root, video)


def _default_auto_project_dir(video: Path) -> Path:
    """Default project directory for the auto-workflow commands.

    Auto-workflow callers (``dub en2zh`` / ``dub ja2zh``) place the
    project next to the source video as ``<video-stem>.dub/`` so the
    operator does not have to think about ``--project-dir`` or read
    ``cfg.paths.dub_root`` to predict where outputs land.

    The fallback is the timestamped ``cfg.paths.dub_root`` project — this
    matches the legacy ``dub run`` behavior so callers without an obvious
    video parent directory still get a project.
    """
    parent = video.resolve().parent
    return parent / f"{video.stem}.dub"


def _bootstrap_state(project_dir: Path, cfg) -> None:
    state_path = project_dir / ".dub" / "state.json"
    if state_path.exists():
        return
    state = new_state(project_dir, cfg)
    info = project_input_info(project_dir)
    state.input["video_path"] = info["video_path"]
    state.input["video_sha256"] = info["video_sha256"]
    state.input["duration_sec"] = info["duration_sec"]
    state.input["translate_mode"] = cfg.translation.mode
    state.input["translated_srt"] = str(cfg.translation.translated_srt) if cfg.translation.translated_srt else None
    save_state(project_dir, state)


def _refresh_runtime_input_state(project_dir: Path, cfg) -> None:
    state = load_state(project_dir)
    state.input["source_lang"] = cfg.defaults.source_lang
    state.input["target_lang"] = cfg.defaults.target_lang
    state.input["translate_mode"] = cfg.translation.mode
    state.input["translated_srt"] = str(cfg.translation.translated_srt) if cfg.translation.translated_srt else None
    save_state(project_dir, state)


def _restore_cfg_from_state_inputs(project_dir: Path, cfg):
    state = load_state(project_dir)
    source_lang = state.input.get("source_lang")
    target_lang = state.input.get("target_lang")
    translate_mode = state.input.get("translate_mode")
    translated_srt_raw = state.input.get("translated_srt")
    translated_srt = Path(translated_srt_raw) if translated_srt_raw else None
    return cfg.merge_cli_overrides(
        source_lang=source_lang,
        target_lang=target_lang,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
    )


def _validate_run_contract(project_dir: Path, cfg) -> None:
    mode = cfg.translation.mode
    translated_srt = cfg.translation.translated_srt
    project_translated_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"

    if mode == "use-existing":
        if translated_srt is None:
            raise UserError("translate-mode=use-existing requires --translated-srt")
        if not translated_srt.exists():
            raise UserError(f"translated SRT not found: {translated_srt}")

    if mode == "skip" and not project_translated_srt.exists():
        raise UserError(
            "translate-mode=skip requires an existing translated subtitle at "
            f"{project_translated_srt}. Use --translate-mode use-existing --translated-srt <path> "
            "for a fresh run, or re-run on an existing project that already has translated subtitles."
        )


def _preflight_route_summary(project_dir: Path, cfg) -> str:
    mode = cfg.translation.mode
    translated_srt = cfg.translation.translated_srt
    project_translated_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"

    if mode == "delegate":
        route = f"translate=delegate provider={cfg.translation.provider}"
    elif mode == "use-existing":
        route = f"translate=use-existing external_srt={translated_srt}"
    else:
        route = f"translate=skip existing_project_srt={project_translated_srt}"

    return (
        "preflight: "
        f"src={cfg.defaults.source_lang} "
        f"tgt={cfg.defaults.target_lang} "
        f"project={project_dir} "
        f"mode={mode} "
        f"route={route}"
    )


def _completion_summary(prefix: str, project_dir: Path) -> str:
    final_mp4 = project_dir / "07_final" / "video_dubbed_stem.mp4"
    return (
        f"{prefix}: project={project_dir} final={final_mp4}\n"
        f"next: dub status --project-dir {project_dir}\n"
        f"next: dub validate --project-dir {project_dir}"
    )


def _which_status(name: str) -> tuple[bool, str]:
    resolved = shutil.which(name)
    return (resolved is not None, resolved or "missing")


def _path_status(path_like: str | Path) -> tuple[bool, str]:
    p = Path(path_like)
    return (p.exists(), str(p))


def _env_status(*names: str) -> tuple[bool, str]:
    seen: list[str] = []
    ordered = []
    for name in names:
        if name in seen:
            continue
        seen.append(name)
        ordered.append(name)
    found = [name for name in ordered if (os.environ.get(name) or "").strip()]
    if found:
        return True, ",".join(found)
    return False, ",".join(ordered)


def _default_operator_config_path() -> Path:
    return Path.home() / ".config" / "dub" / "config.yaml"


def _load_yaml_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise UserError(f"config file must be a YAML mapping: {path}")
    return raw


def _write_yaml_dict(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / "bin" / "python"


# Names of secrets we know how to auto-recover from the user's interactive
# shell rc files. We do this on a best-effort basis because Hermes / CI
# shells do not load ~/.zshrc, and `GOOGLE_API_KEY` exported there is not
# visible to `uv run` subprocesses. Reading the rc file directly is a
# small, explicit operator ergonomics fix — it never overrides an
# already-set value, and is skipped silently if the rc file is absent.
_AUTO_RECOVER_SECRET_NAMES: tuple[str, ...] = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
)


def _auto_recover_missing_secrets(names: tuple[str, ...] = _AUTO_RECOVER_SECRET_NAMES) -> list[str]:
    """Best-effort: if any of ``names`` is unset and the user has the
    corresponding export line in a known shell rc, set it for this process.

    Returns the list of names that were recovered.

    This is intentionally narrow:

    * Only the secrets that ``dub doctor`` reports on are touched.
    * Only the user's own rc files are read (``~/.zshrc``, ``~/.bashrc``).
    * Existing values are never overridden.
    * On any parse failure, we silently skip — the doctor will surface the
      real status and the operator can fix it manually.
    """
    recovered: list[str] = []
    for name in names:
        if (os.environ.get(name) or "").strip():
            continue
        for rc in (Path.home() / ".zshrc", Path.home() / ".bashrc"):
            if not rc.exists():
                continue
            try:
                for raw in rc.read_text(errors="ignore").splitlines():
                    line = raw.strip()
                    prefix = f"export {name}="
                    if not line.startswith(prefix):
                        continue
                    value = line[len(prefix):].strip().strip('"').strip("'")
                    if value:
                        os.environ[name] = value
                        recovered.append(name)
                        break
            except OSError:
                continue
            if name in recovered:
                break
    return recovered


@click.group()
@click.version_option()
def main():
    """video-dub-cli — single command to dub any video."""
    pass


def _run_pipeline_command(
    video: Path,
    *,
    source_lang: str | None,
    target_lang: str | None,
    project_dir: Path | None,
    config_path: Path | None,
    translate_mode: str,
    translated_srt: Path | None,
    vocal_gain: float | None,
    inst_gain: float | None,
    keep_fulltrack: bool,
    yes: bool,
) -> None:
    try:
        cfg = load_config(config_path)
        cfg = cfg.merge_cli_overrides(
            source_lang=source_lang,
            target_lang=target_lang,
            vocal_gain=vocal_gain,
            inst_gain=inst_gain,
            keep_fulltrack=keep_fulltrack,
            translate_mode=translate_mode,
            translated_srt=translated_srt,
        )
        pdir = _prepare_project(video, str(project_dir) if project_dir else None, cfg)
        _validate_run_contract(pdir, cfg)
        click.echo(_preflight_route_summary(pdir, cfg))
        _bootstrap_state(pdir, cfg)
        _refresh_runtime_input_state(pdir, cfg)
        run_pipeline(pdir, cfg, yes=yes)
    except UserError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(_completion_summary("run complete", pdir))


@main.command()
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option("--source-lang", "source_lang", default=None)
@click.option("--target-lang", "target_lang", default=None)
@click.option("--project-dir", type=click.Path(path_type=Path), default=None)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--translate-mode",
    type=click.Choice(["delegate", "skip", "use-existing"]),
    default="delegate",
)
@click.option("--translated-srt", type=click.Path(path_type=Path), default=None)
@click.option("--vocal-gain", type=float, default=None)
@click.option("--inst-gain", type=float, default=None)
@click.option("--keep-fulltrack", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
def run(video, source_lang, target_lang, project_dir, config_path,
        translate_mode, translated_srt, vocal_gain, inst_gain,
        keep_fulltrack, yes):
    """Run full dubbing pipeline. VIDEO is the source mp4 path."""
    _run_pipeline_command(
        video,
        source_lang=source_lang,
        target_lang=target_lang,
        project_dir=project_dir,
        config_path=config_path,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
        vocal_gain=vocal_gain,
        inst_gain=inst_gain,
        keep_fulltrack=keep_fulltrack,
        yes=yes,
    )


@main.command(name="en2zh")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option("--project-dir", type=click.Path(path_type=Path), default=None,
              help="Project directory (default: <video-stem>.dub/ next to the input video).")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--translate-mode",
    type=click.Choice(["delegate", "skip", "use-existing"]),
    default="delegate",
)
@click.option("--translated-srt", type=click.Path(path_type=Path), default=None)
@click.option("--vocal-gain", type=float, default=None)
@click.option("--inst-gain", type=float, default=None)
@click.option("--keep-fulltrack", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
def en2zh(video, project_dir, config_path, translate_mode, translated_srt, vocal_gain, inst_gain, keep_fulltrack, yes):
    """Run the common English→Chinese operator flow.

    The default zero-flag invocation runs the full pipeline end-to-end:
    project directory is auto-derived from the video, source/target
    languages are hard-coded to en→zh, and translate-mode defaults to
    delegate (the existing happy path). Advanced knobs (--project-dir,
    --translate-mode, --translated-srt, --vocal-gain, --inst-gain,
    --keep-fulltrack) remain available for explicit-control overrides.
    """
    effective_project_dir = project_dir if project_dir is not None else _default_auto_project_dir(video)
    _run_pipeline_command(
        video,
        source_lang="en",
        target_lang="zh",
        project_dir=effective_project_dir,
        config_path=config_path,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
        vocal_gain=vocal_gain,
        inst_gain=inst_gain,
        keep_fulltrack=keep_fulltrack,
        yes=yes,
    )


@main.command(name="ja2zh")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option("--project-dir", type=click.Path(path_type=Path), default=None,
              help="Project directory (default: <video-stem>.dub/ next to the input video).")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--translate-mode",
    type=click.Choice(["delegate", "skip", "use-existing"]),
    default="delegate",
)
@click.option("--translated-srt", type=click.Path(path_type=Path), default=None)
@click.option("--vocal-gain", type=float, default=None)
@click.option("--inst-gain", type=float, default=None)
@click.option("--keep-fulltrack", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
def ja2zh(video, project_dir, config_path, translate_mode, translated_srt, vocal_gain, inst_gain, keep_fulltrack, yes):
    """Run the common Japanese→Chinese operator flow.

    The default zero-flag invocation runs the full pipeline end-to-end:
    project directory is auto-derived from the video, source/target
    languages are hard-coded to ja→zh, and translate-mode defaults to
    delegate (the existing happy path). Advanced knobs (--project-dir,
    --translate-mode, --translated-srt, --vocal-gain, --inst-gain,
    --keep-fulltrack) remain available for explicit-control overrides.
    """
    effective_project_dir = project_dir if project_dir is not None else _default_auto_project_dir(video)
    _run_pipeline_command(
        video,
        source_lang="ja",
        target_lang="zh",
        project_dir=effective_project_dir,
        config_path=config_path,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
        vocal_gain=vocal_gain,
        inst_gain=inst_gain,
        keep_fulltrack=keep_fulltrack,
        yes=yes,
    )


@main.command(name="resume")
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def resume_cmd(project_dir, config_path):
    """Resume an interrupted pipeline from last successful stage."""
    cfg = load_config(config_path)
    project_dir.mkdir(parents=True, exist_ok=True)
    if not (project_dir / "01_raw_video" / "video.mp4").exists():
        click.echo(f"resume: project={project_dir} (no source video)")
        return
    _bootstrap_state(project_dir, cfg)
    cfg = _restore_cfg_from_state_inputs(project_dir, cfg)
    _refresh_runtime_input_state(project_dir, cfg)
    run_pipeline(project_dir, cfg, yes=True)
    click.echo(_completion_summary("resume complete", project_dir))


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
def status(project_dir):
    """Show stage-by-stage pipeline status."""
    try:
        state = load_state(project_dir)
    except FileNotFoundError:
        click.echo(f"status: project={project_dir} (no state)")
        return
    for name, st in state.stages.items():
        click.echo(f"{name}: {st.status} attempts={st.attempts}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--keep-source/--remove-source", default=True)
@click.option("--stage", type=int, default=None)
def clean(project_dir, keep_source, stage):
    """Clean partial pipeline artifacts."""
    if stage is None:
        targets = [d for d in STAGE_DIRS if keep_source or d != "01_raw_video"] + [".dub"]
    else:
        stage_map = {
            1: ["02_stems"],
            2: ["03_asr"],
            3: ["04_ref_audio"],
            4: ["05_translate", "05_translated_srt"],
            5: ["06_tts_wav"],
            6: ["07_final"],
        }
        targets = stage_map.get(stage, [])
    for rel in targets:
        target = project_dir / rel
        if target.exists():
            shutil.rmtree(target)
        if rel != ".dub":
            target.mkdir(parents=True, exist_ok=True)
    click.echo(f"clean complete: project={project_dir} stage={stage}")


def _validate_translated_subtitle_contract(project_dir: Path, state) -> tuple[bool, str]:
    mode = state.input.get("translate_mode") or "delegate"
    translate_stage = state.stages.get("04_translate")
    translate_status = translate_stage.status if translate_stage else "unknown"
    zh_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"

    requires_translated_srt = translate_status == "done" and mode in {"delegate", "use-existing"}

    if requires_translated_srt and not zh_srt.exists():
        return False, (
            "translated subtitle required but missing: "
            f"mode={mode} translate_status={translate_status} path={zh_srt}"
        )

    return True, f"mode={mode} translate_status={translate_status}"


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
def validate(project_dir):
    """Validate project structure and outputs."""
    missing = []
    for rel in ["01_raw_video", "02_stems", "03_asr", "04_ref_audio", "05_translate", "05_translated_srt", "06_tts_wav", "07_final", ".dub"]:
        if not (project_dir / rel).exists():
            missing.append(rel)
    if missing:
        click.echo(f"validate: project={project_dir} missing={','.join(missing)}")
        return
    try:
        state = load_state(project_dir)
        stage_count = len(state.stages)
    except FileNotFoundError:
        stage_count = 0
        click.echo(f"validate ok: project={project_dir} stages={stage_count} mode=unknown")
        return

    ok, detail = _validate_translated_subtitle_contract(project_dir, state)
    if not ok:
        raise click.ClickException(f"validate failed: project={project_dir} {detail}")

    click.echo(f"validate ok: project={project_dir} stages={stage_count} {detail}")


@main.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def doctor(config_path):
    """Check standalone runtime readiness and report missing dependencies."""
    cfg = load_config(config_path)

    # Best-effort auto-recovery of Gemini key from interactive shell rc files.
    # This is a small operator-ergonomics fix for shells (Hermes / CI) that do
    # not load ~/.zshrc. We never override an already-set value.
    auto_recovered = _auto_recover_missing_secrets()

    checks: list[tuple[str, bool, str]] = []
    ffmpeg_ok, ffmpeg_detail = _which_status("ffmpeg")
    checks.append(("ffmpeg", ffmpeg_ok, ffmpeg_detail))
    ffprobe_ok, ffprobe_detail = _which_status("ffprobe")
    checks.append(("ffprobe", ffprobe_ok, ffprobe_detail))
    scripts_dir = pipeline_scripts_dir()
    skills_ok, skills_detail = _path_status(scripts_dir)
    checks.append(("repo_pipeline_scripts", skills_ok, skills_detail))
    gemini_ok, gemini_detail = _env_status(cfg.translation.api_env_var, "GOOGLE_API_KEY", "GEMINI_API_KEY")
    checks.append(("gemini_api_key", gemini_ok, gemini_detail))

    # Real-backend gates: the dependencies that the repo-owned ASR + Gemini
    # translation + VoxCPM need at runtime. These are pulled in by
    # `uv sync --extra all` but may be missing on a freshly-cloned host.
    # Reporting them here means `dub doctor` is the single source of truth
    # for the operator.
    from dub.tts_engines import diagnostics as _diag
    qwen_status, qwen_detail = _diag.python_imports("qwen3_asr_mlx")
    checks.append(("py:qwen3_asr_mlx", qwen_status == "ok", qwen_detail))
    sf_status, sf_detail = _diag.python_imports("soundfile")
    checks.append(("py:soundfile", sf_status == "ok", sf_detail))
    pydub_status, pydub_detail = _diag.python_imports("pydub")
    checks.append(("py:pydub", pydub_status == "ok", pydub_detail))
    vad_status, vad_detail = _diag.python_imports("silero_vad")
    checks.append(("py:silero_vad", vad_status == "ok", vad_detail))
    ggenai_status, ggenai_detail = _diag.python_imports("google.genai")
    checks.append(("py:google_genai", ggenai_status == "ok", ggenai_detail))
    tcdc_status, tcdc_detail = _diag.python_imports("torchcodec")
    checks.append(("py:torchcodec", tcdc_status == "ok", tcdc_detail))

    all_ok = True
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        click.echo(f"{name}: {status} ({detail})")
        if not ok:
            all_ok = False

    if auto_recovered:
        click.echo(
            f"note: auto-recovered {','.join(auto_recovered)} from interactive shell rc "
            "(Hermes / CI shells do not load ~/.zshrc; re-run in a real zsh to set it permanently)"
        )

    readiness_by_backend = {
        "omnivoice": omnivoice_readiness(cfg),
        "voxcpme": voxcpme_readiness(cfg),
    }
    click.echo("tts_backends:")
    for backend_name in builtin_backends():
        readiness = readiness_by_backend[backend_name]
        status = "READY" if readiness.ready else "BLOCKED"
        click.echo(f"  {backend_name}: {status} ({readiness.detail})")
        for gate, gate_status, detail in readiness.checks:
            click.echo(f"    - {gate}: {gate_status} ({detail})")

    if all_ok:
        click.echo("doctor ok: ready for `dub en2zh` / `dub ja2zh`")
        click.echo("doctor next: run `dub en2zh <VIDEO>` (or `dub ja2zh <VIDEO>`) to dub end-to-end")
    else:
        raise click.ClickException("doctor found missing prerequisites")


@main.command()
def bootstrap():
    """Print bootstrap guidance for repo-only setup and backend preparation."""
    click.echo("bootstrap: repo package install is uv-managed; run `uv sync --extra all` for the canonical dub venv (CLI + ASR + Gemini + VoxCPM)")
    click.echo("bootstrap: install system tools ffmpeg/ffprobe before real media runs")
    click.echo("bootstrap: repo-owned ASR ships in `src/qwenasr_mlx_cli`; do not install a separate `qwenasr-mlx` CLI for the canonical path")
    click.echo("bootstrap: the canonical ASR runtime lives in the dub venv and needs qwen3-asr-mlx + soundfile + pydub + silero-vad + torchcodec (all pulled in by `uv sync --extra all`)")
    click.echo("bootstrap: copy `.env.example` to your shell env setup and export GOOGLE_API_KEY (or GEMINI_API_KEY) before Gemini translation")
    click.echo("bootstrap: if you use zsh and your keys live in ~/.zshrc, you may need to source it before `uv run` because Hermes / CI shells do not load interactive rc files")
    click.echo("bootstrap: repo-owned pipeline scripts live under vendor/pipeline_scripts; no extra path config is required")
    click.echo("bootstrap: real backend also needs google-genai for Gemini translation — it is pulled in by `uv sync --extra all`")
    click.echo("bootstrap: OmniVoice route uses the configured Python interpreter (default: python3) with required packages installed")
    click.echo("bootstrap: OmniVoice model code is vendored in this repo; install its runtime deps in the configured OmniVoice interpreter with `uv sync --extra tts-omnivoice`")
    click.echo("bootstrap: or run `dub bootstrap-omnivoice` to create a dedicated interpreter and wire paths.omnivoice_python automatically")
    click.echo("bootstrap: VoxCPM route also uses a dedicated Python interpreter when fully productized")
    click.echo("bootstrap: run `dub bootstrap-voxcpm` to create a dedicated interpreter and wire paths.voxcpme_python automatically")
    click.echo("bootstrap: VoxCPM still requires a local server on 127.0.0.1:8808 until the repo-owned server entrypoint is fully wired")
    click.echo("bootstrap: the only required external secret is GOOGLE_API_KEY / GEMINI_API_KEY")
    click.echo("bootstrap: run `dub doctor` to verify every gate before your first real run")


def _bootstrap_backend_venv(*, backend_name: str, extra_name: str, path_key: str, venv_path: Path, config_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise click.ClickException(f"bootstrap-{backend_name} requires `uv` on PATH")

    venv_path = venv_path.expanduser().resolve()
    config_path = config_path.expanduser().resolve()

    click.echo(f"bootstrap-{backend_name}: repo={repo_root}")
    click.echo(f"bootstrap-{backend_name}: target_venv={venv_path}")
    click.echo(f"bootstrap-{backend_name}: config={config_path}")

    subprocess.run([uv_bin, "venv", str(venv_path)], check=True, cwd=str(repo_root))
    py = _venv_python(venv_path)
    if not py.exists():
        raise click.ClickException(f"bootstrap-{backend_name} created no python at {py}")

    subprocess.run(
        [uv_bin, "pip", "install", "--python", str(py), "-e", f".[{extra_name}]"],
        check=True,
        cwd=str(repo_root),
    )

    data = _load_yaml_dict(config_path)
    paths = data.get("paths") or {}
    if not isinstance(paths, dict):
        raise UserError(f"config paths section must be a YAML mapping: {config_path}")
    paths[path_key] = str(py)
    data["paths"] = paths
    _write_yaml_dict(config_path, data)
    return py


@main.command(name="bootstrap-omnivoice")
@click.option(
    "--venv-path",
    type=click.Path(path_type=Path),
    default=Path(".venvs") / "omnivoice",
    show_default=True,
    help="Target virtualenv directory for the dedicated OmniVoice interpreter.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="YAML config file to update with paths.omnivoice_python (default: ~/.config/dub/config.yaml).",
)
def bootstrap_omnivoice(venv_path, config_path):
    """Create/update a dedicated OmniVoice venv and wire config automatically."""
    config_path = (config_path or _default_operator_config_path()).expanduser().resolve()
    py = _bootstrap_backend_venv(
        backend_name="omnivoice",
        extra_name="tts-omnivoice",
        path_key="omnivoice_python",
        venv_path=venv_path,
        config_path=config_path,
    )
    click.echo(f"bootstrap-omnivoice: installed video-dub-cli[tts-omnivoice] into {venv_path}")
    click.echo(f"bootstrap-omnivoice: wrote paths.omnivoice_python={py} into {config_path}")
    click.echo(f"bootstrap-omnivoice: next run `uv run dub doctor --config {config_path}`")


@main.command(name="bootstrap-voxcpm")
@click.option(
    "--venv-path",
    type=click.Path(path_type=Path),
    default=Path(".venvs") / "voxcpm",
    show_default=True,
    help="Target virtualenv directory for the dedicated VoxCPM interpreter.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="YAML config file to update with paths.voxcpme_python (default: ~/.config/dub/config.yaml).",
)
def bootstrap_voxcpm(venv_path, config_path):
    """Create/update a dedicated VoxCPM venv and wire config automatically."""
    config_path = (config_path or _default_operator_config_path()).expanduser().resolve()
    py = _bootstrap_backend_venv(
        backend_name="voxcpm",
        extra_name="tts-vox",
        path_key="voxcpme_python",
        venv_path=venv_path,
        config_path=config_path,
    )
    click.echo(f"bootstrap-voxcpm: installed video-dub-cli[tts-vox] into {venv_path}")
    click.echo(f"bootstrap-voxcpm: wrote paths.voxcpme_python={py} into {config_path}")
    click.echo("bootstrap-voxcpm: note the local server still needs to be started separately until the repo-owned server entrypoint lands")
    click.echo(f"bootstrap-voxcpm: next run `uv run dub doctor --config {config_path}`")
