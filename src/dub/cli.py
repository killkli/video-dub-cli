from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import click

from dub.config import load_config
from dub.errors import UserError
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
        route = "translate=delegate (committed provider route)"
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


@click.group()
@click.version_option()
def main():
    """video-dub-cli — single command to dub any video."""
    pass


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
    click.echo(f"run complete: project={pdir}")


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
    click.echo(f"resume complete: project={project_dir}")


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

    checks: list[tuple[str, bool, str]] = []
    ffmpeg_ok, ffmpeg_detail = _which_status("ffmpeg")
    checks.append(("ffmpeg", ffmpeg_ok, ffmpeg_detail))
    ffprobe_ok, ffprobe_detail = _which_status("ffprobe")
    checks.append(("ffprobe", ffprobe_ok, ffprobe_detail))
    qwen_ok, qwen_detail = _which_status(str(cfg.paths.qwenasr_cli))
    checks.append(("qwenasr_cli", qwen_ok, qwen_detail))
    py_ok, py_detail = _which_status(str(cfg.paths.omnivoice_python))
    checks.append(("omnivoice_python", py_ok, py_detail))
    tts_dir = cfg.paths.tts_engines_dir or cfg.paths.skills_dir
    skills_ok, skills_detail = _path_status(tts_dir)
    checks.append(("tts_engines_dir", skills_ok, skills_detail))
    gemini_ok, gemini_detail = _env_status(cfg.translation.api_env_var, "GOOGLE_API_KEY", "GEMINI_API_KEY")
    checks.append(("gemini_api_key", gemini_ok, gemini_detail))

    all_ok = True
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        click.echo(f"{name}: {status} ({detail})")
        if not ok:
            all_ok = False

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
        click.echo("doctor ok: standalone prerequisites look ready")
    else:
        raise click.ClickException("doctor found missing prerequisites")


@main.command()
def bootstrap():
    """Print bootstrap guidance for repo-only setup and backend preparation."""
    click.echo("bootstrap: repo package install is uv-managed; run `uv sync --extra all` for the full standalone stack")
    click.echo("bootstrap: install system tools ffmpeg/ffprobe before real media runs")
    click.echo("bootstrap: copy `.env.example` to your shell env setup and export GOOGLE_API_KEY (or GEMINI_API_KEY) before Gemini translation")
    click.echo("bootstrap: non-TTS pipeline scripts are now repo-owned under vendor/pipeline_scripts")
    click.echo("bootstrap: OmniVoice route expects `paths.omnivoice_python` to point at a Python with torch + omnivoice installed")
    click.echo("bootstrap: VoxCPM route expects the dub venv to include gradio_client + opencc, and a local VoxCPM server on 127.0.0.1:8808")
    click.echo("bootstrap: set `paths.tts_engines_dir` if your TTS wrapper scripts are not in vendor/pipeline_scripts")
