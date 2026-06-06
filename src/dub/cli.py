from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
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


def _preflight_route_summary_payload(project_dir: Path, cfg) -> str:
    """Return the ``mode=... route=...`` half of the legacy preflight summary.

    This is shared between :func:`_preflight_route_summary` (which
    keeps the full preflight line shape for backward compatibility
    with existing tests) and :func:`_run_preflight` (which now bundles
    the per-gate status into one line).
    """
    mode = cfg.translation.mode
    translated_srt = cfg.translation.translated_srt
    project_translated_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"

    if mode == "delegate":
        route = f"translate=delegate provider={cfg.translation.provider}"
    elif mode == "use-existing":
        route = f"translate=use-existing external_srt={translated_srt}"
    else:
        route = f"translate=skip existing_project_srt={project_translated_srt}"

    return f"mode={mode} route={route}"


def _preflight_route_summary(project_dir: Path, cfg) -> str:
    return (
        "preflight: "
        f"src={cfg.defaults.source_lang} "
        f"tgt={cfg.defaults.target_lang} "
        f"project={project_dir} "
        f"{_preflight_route_summary_payload(project_dir, cfg)}"
    )


# Route → TTS backend mapping. This is the canonical dispatch table for
# the one-command workflow: dub auto / dub en2zh / dub ja2zh all funnel
# through the same preflight contract, and the source-lang determines
# which TTS backend gate must be READY before stage execution starts.
#
# Keeping this in one place prevents drift: adding a new auto-route
# means appending to this mapping and to ``_resolve_auto_source_lang``.
# Wave 3 (T3) — the resolver now also dispatches to ``_detect_auto_source_lang``
# when the explicit ``--source-lang`` flag is absent, so the contract is
# "explicit override > auto detect > early fail with re-run guidance".
_SUPPORTED_AUTO_SOURCE_LANGS: tuple[str, ...] = ("en", "ja")
_TTS_BACKEND_FOR_SOURCE: dict[str, str] = {
    "en": "omnivoice",
    "ja": "voxcpme",
}


def _tts_backend_for_source(source_lang: str) -> str:
    """Return the TTS backend name that owns ``source_lang``.

    Raises :class:`UserError` for source languages outside the
    productized auto-workflow surface. The route-specific commands
    (``dub en2zh`` / ``dub ja2zh``) hard-code their own source lang,
    so this helper is only exercised by the centralized preflight
    contract and ``dub auto`` callers.
    """
    backend = _TTS_BACKEND_FOR_SOURCE.get(source_lang)
    if backend is None:
        raise UserError(
            f"no TTS route registered for source_lang={source_lang!r}; "
            f"supported: {','.join(_SUPPORTED_AUTO_SOURCE_LANGS)}"
        )
    return backend


def _format_preflight_gate(name: str, ok: bool, detail: str) -> str:
    status = "ok" if ok else "fail"
    return f"{name}={status}({detail})"


def _run_preflight(project_dir: Path, cfg, source_lang: str, route_basis: str | None = None) -> str:
    """Run the centralized route-specific preflight checks.

    This is the single contract shared by ``dub auto``, ``dub en2zh``,
    and ``dub ja2zh`` — every gate that the auto-workflow needs is
    verified here before any stage is executed. On success it returns
    a one-line summary that the caller echoes; on failure it raises
    :class:`UserError` listing *every* failing gate so the operator
    can fix all blockers in one pass instead of being drip-fed.

    Current gates:

    * ``ffmpeg`` / ``ffprobe`` — must be on ``$PATH``; everything from
      stem extraction to final mux needs them, and a missing
      ffmpeg is the single most common operator footgun.
    * ``pipeline_scripts`` — the repo-owned vendored runtime scripts
      must be on disk.
    * ``gemini_key`` — required when ``translate-mode=delegate``; we
      honor the configured ``api_env_var`` and the documented fall-back
      names so the operator does not have to know which one we look at.
    * ``tts.<backend>`` — the TTS backend that owns the resolved
      route must be ``READY`` per :class:`TtsReadiness`. We do **not**
      re-probe every backend: only the one the route actually drives.

    New auto-workflow surfaces (e.g. a new source language) should
    extend ``_TTS_BACKEND_FOR_SOURCE``; the gate logic itself does
    not need to change.
    """
    # Best-effort: pull secrets from the operator's interactive rc
    # before we check the gemini gate. We mirror what `dub doctor`
    # does so a one-command `dub auto` works in Hermes / CI shells
    # that do not source ~/.zshrc on their own.
    _auto_recover_missing_secrets()

    gates: list[tuple[str, bool, str]] = []

    ffmpeg_ok, ffmpeg_detail = _which_status("ffmpeg")
    gates.append(("ffmpeg", ffmpeg_ok, ffmpeg_detail))
    ffprobe_ok, ffprobe_detail = _which_status("ffprobe")
    gates.append(("ffprobe", ffprobe_ok, ffprobe_detail))

    scripts_dir = pipeline_scripts_dir()
    scripts_ok, scripts_detail = _path_status(scripts_dir)
    gates.append(("pipeline_scripts", scripts_ok, scripts_detail))

    mode = cfg.translation.mode
    if mode == "delegate":
        gemini_ok, gemini_detail = _env_status(
            cfg.translation.api_env_var,
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
        )
        gates.append(("gemini_key", gemini_ok, gemini_detail))

    backend_name = _tts_backend_for_source(source_lang)
    if backend_name == "omnivoice":
        tts_readiness = omnivoice_readiness(cfg)
    elif backend_name == "voxcpme":
        tts_readiness = voxcpme_readiness(cfg)
    else:  # pragma: no cover - guarded by _tts_backend_for_source
        tts_readiness = None
    if tts_readiness is not None:
        gates.append((f"tts.{backend_name}", tts_readiness.ready, tts_readiness.detail))

    failed = [(name, detail) for name, ok, detail in gates if not ok]
    if failed:
        bullets = "\n".join(
            f"  - {name}: {detail}" for name, detail in failed
        )
        raise UserError(
            f"preflight failed for source_lang={source_lang} "
            f"project={project_dir} — fix the following gate(s) "
            f"and re-run, or run `dub doctor` for the full readiness report:\n"
            f"{bullets}"
        )

    route_summary = _preflight_route_summary_payload(project_dir, cfg)
    parts = " ".join(
        _format_preflight_gate(name, ok, detail) for name, ok, detail in gates
    )
    basis_token = f" route_basis={route_basis}" if route_basis else ""
    return (
        f"preflight: src={source_lang} tgt={cfg.defaults.target_lang} "
        f"project={project_dir} {route_summary} {parts}{basis_token}"
    )


def _final_output_path(project_dir: Path) -> Path:
    return project_dir / "07_final" / "video_dubbed_stem.mp4"


def _recovery_hints(project_dir: Path) -> str:
    return (
        f"next: dub resume --project-dir {project_dir}\n"
        f"next: dub status --project-dir {project_dir}\n"
        f"next: dub validate --project-dir {project_dir}"
    )


def _operator_paths_summary(prefix: str, project_dir: Path) -> str:
    final_mp4 = _final_output_path(project_dir)
    return (
        f"{prefix}: project={project_dir} final={final_mp4}\n"
        f"{_recovery_hints(project_dir)}"
    )


def _completion_summary(prefix: str, project_dir: Path) -> str:
    return _operator_paths_summary(prefix, project_dir)


@dataclass(frozen=True)
class AutoRouteDecision:
    """Operator-visible verdict from the auto route detector.

    ``source_lang`` is the normalized source language (``"en"`` / ``"ja"``)
    when the detector is confident; ``None`` when detection is ambiguous or
    not confidently reducible to the supported auto routes. ``basis`` is a
    short stable string that ``dub auto`` echoes on the preflight line so
    operators can audit why a particular route was chosen without re-running
    with ``--debug``.
    """

    source_lang: str | None
    basis: str


# How many seconds of the input audio we probe for language detection.
# 30s is enough to get a representative ASR sample for a confident
# en/ja call without paying for full-length transcription; anything
# shorter and we risk ASR garbage on intros / title cards.
_AUTO_PROBE_SECONDS = 30


# Unicode ranges used for the post-ASR text classifier. We deliberately
# stick to script-level heuristics here (not a trained langid model)
# because the only thing the auto route needs to disambiguate is
# Latin-script (English) vs. CJK kana/kanji (Japanese) for the common
# youtube → zh dubbing path.
_JA_CHAR_PATTERN = re.compile(
    r"[\u3040-\u309F"   # hiragana
    r"\u30A0-\u30FF"     # katakana
    r"\u4E00-\u9FFF"     # CJK unified ideographs (kanji / kanji-like)
    r"\uFF66-\uFF9D"     # half-width katakana
    r"]"
)
_LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")


def _classify_probe_text(text: str) -> str | None:
    """Classify ASR probe output as ``"en"``, ``"ja"``, or ``None`` (ambiguous).

    The classifier is intentionally simple: it counts script-bearing
    characters and picks the dominant one. Mixed / sparse text returns
    ``None`` so the CLI layer can fail fast.
    """
    if not text or not text.strip():
        return None
    ja_count = len(_JA_CHAR_PATTERN.findall(text))
    latin_count = len(_LATIN_CHAR_PATTERN.findall(text))
    if ja_count == 0 and latin_count == 0:
        return None
    if ja_count == 0:
        return "en"
    if latin_count == 0:
        return "ja"
    # Mixed: pick the dominant script, but only if it dominates by
    # at least 3x. Mixed-script ASR is the strongest signal that the
    # source is neither cleanly en nor ja (e.g. code-switched content,
    # Korean, Chinese, etc.) and we should defer to the operator.
    if ja_count >= 3 * latin_count:
        return "ja"
    if latin_count >= 3 * ja_count:
        return "en"
    return None


def _extract_probe_audio(video: Path, seconds: int = _AUTO_PROBE_SECONDS) -> Path | None:
    """Extract a short mono-16k WAV from ``video`` for the language probe.

    Returns the temp WAV path on success, or ``None`` when ``ffmpeg`` is
    not on ``$PATH`` / fails — callers should treat ``None`` as
    "detector unavailable" and surface that as an ambiguous decision.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    tmp = Path(tempfile.mkstemp(prefix="dub_autoprobe_", suffix=".wav")[1])
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(video),
                "-t", str(seconds),
                "-vn", "-ac", "1", "-ar", "16000",
                "-f", "wav", str(tmp),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            return None
        return tmp
    except Exception:
        return None


def _transcribe_probe_audio(wav: Path) -> str:
    """Run the repo ASR pipeline on a short audio probe.

    Imports the qwenasr_mlx_cli pipeline lazily so ``dub auto`` does not
    require the ASR backend to be installed in environments that only
    use route-specific commands (``dub en2zh`` / ``dub ja2zh`` /
    ``dub run``).

    The probe is always run with ``language=None`` (let the model pick)
    and with a plain-text output so the classifier can see the actual
    characters — SRT timestamps are noise for language detection.
    """
    from qwenasr_mlx_cli.pipelines.transcribe import run_transcription

    return run_transcription(
        input_path=wav,
        backend_name="mlx",
        output_format="txt",
        language=None,
        prompt=None,
        subtitle_config=None,
        convert_simplified_to_traditional=False,
    )


def _detect_auto_source_lang(video: Path, cfg) -> AutoRouteDecision:
    """Decide the source language of ``video`` for ``dub auto``.

    Implementation strategy (head-probe):

    1. Extract up to ``_AUTO_PROBE_SECONDS`` of mono-16k audio from
       ``video`` via ``ffmpeg``.
    2. Run the repo-owned ASR pipeline (``qwenasr_mlx_cli``) on the
       probe with no language hint, so the model can pick freely.
    3. Classify the transcribed text by character script: Japanese
       kana/kanji → ``"ja"``, ASCII/Latin → ``"en"``, mixed / sparse
       / unrecognised → ambiguous.

    Failure modes that the CLI layer turns into an early UserError:

    * ``ffmpeg`` missing → ``"ambiguous:no-ffmpeg"``
    * ASR backend unavailable → ``"ambiguous:asr-unavailable"``
    * ASR probe produced no text / non-recognisable script →
      ``"ambiguous:low-confidence"``

    Any unexpected runtime error is re-raised — the CLI layer maps it
    to a fail-fast error rather than silently falling back to a
    config default. This is the contract T2 pins: ``dub auto`` is
    not allowed to silently degrade to ``cfg.defaults.source_lang``.
    """
    if not video.exists():
        raise UserError(f"input video not found: {video}")

    wav = _extract_probe_audio(video)
    if wav is None:
        return AutoRouteDecision(
            source_lang=None,
            basis="ambiguous:no-ffmpeg",
        )
    try:
        text = _transcribe_probe_audio(wav)
    except Exception as exc:
        return AutoRouteDecision(
            source_lang=None,
            basis=f"ambiguous:asr-unavailable:{type(exc).__name__}",
        )
    finally:
        try:
            wav.unlink(missing_ok=True)
        except Exception:
            pass

    classified = _classify_probe_text(text)
    if classified is None:
        return AutoRouteDecision(
            source_lang=None,
            basis="ambiguous:low-confidence",
        )
    return AutoRouteDecision(
        source_lang=classified,
        basis=f"detected:{classified}-asr-head",
    )


def _normalize_explicit_source_lang(source_lang: str | None) -> str | None:
    """Normalize a user-supplied ``--source-lang`` value to ``"en"``/``"ja"``/``None``.

    ``None`` means "no explicit flag — caller should run the detector".
    """
    if source_lang is None:
        return None
    candidate = source_lang.strip().lower()
    if candidate in {"en", "english"}:
        return "en"
    if candidate in {"ja", "jp", "jpn", "japanese"}:
        return "ja"
    raise UserError(
        f"dub auto --source-lang {source_lang!r} is not supported "
        f"(supported: en, ja). Re-run with --source-lang en|ja."
    )


def _resolve_auto_route(video: Path, source_lang: str | None, cfg) -> AutoRouteDecision:
    """Apply the wave-3 precedence: explicit > auto detect > early fail.

    Branches:

    1. Explicit ``--source-lang`` flag (normalized) → return immediately
       with a ``"override:..."`` basis so the preflight line tells the
       operator the detector was bypassed.
    2. No flag → call :func:`_detect_auto_source_lang` and return its
       decision verbatim.
    3. The detector returns ``source_lang=None`` (ambiguous) → the CLI
       layer surfaces this as an early UserError; we do *not* fall
       back to ``cfg.defaults.source_lang`` because that was the old
       route-aware behavior T3 explicitly retires.
    """
    explicit = _normalize_explicit_source_lang(source_lang)
    if explicit is not None:
        return AutoRouteDecision(
            source_lang=explicit,
            basis="override:explicit-flag",
        )
    return _detect_auto_source_lang(video, cfg)


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
    """video-dub-cli — single command to dub any video.

    First-time operator? Run these three commands in order from the repo
    root:

    \b
        uv sync --extra all        # build the canonical dub venv
        uv run dub doctor          # confirm EN / JA lanes are ready
        uv run dub auto <VIDEO>    # dub end-to-end (auto-detects EN vs JA)

    For more detail see QUICKSTART.md and docs/operator-runbook.md.
    """
    pass


# Friendly labels for the human-readable route summary line. We keep the
# canonical ISO codes (en/ja) in the machine-oriented preflight line so
# existing audits and tests keep working; this mapping is only used for
# the operator-facing one-glance summary.
_SOURCE_LANG_LABELS: dict[str, str] = {
    "en": "English",
    "ja": "Japanese",
}
_TARGET_LANG_LABELS: dict[str, str] = {
    "zh": "Chinese (Traditional)",
}
_TTS_BACKEND_LABELS: dict[str, str] = {
    "omnivoice": "OmniVoice (local TTS)",
    "voxcpme": "VoxCPM (local TTS)",
}
_TRANSLATION_PROVIDER_LABELS: dict[str, str] = {
    "gemini": "Gemini (Google translation API)",
}


def _route_basis_human(basis: str | None) -> str:
    """Turn the internal route_basis token into a one-line operator-friendly
    explanation of how the route was chosen.

    Examples:

        override:explicit-flag     -> "source language: explicit --source-lang flag"
        detected:en-asr-head       -> "source language: picked from probe (basis=detected:en-asr-head)"
        ambiguous:no-ffmpeg        -> "source language: ambiguous (basis=ambiguous:no-ffmpeg)"

    The "detected" branch intentionally says "picked from probe" rather
    than "auto-detected" so the human summary does not collide with the
    ``auto-detect:`` probe-progress prefix on ``dub auto``'s stderr.
    """
    if not basis:
        return "source language: explicit (no detector ran)"
    if basis.startswith("override:"):
        return f"source language: explicit --source-lang flag (basis={basis})"
    if basis.startswith("detected:"):
        # detected:<lang>-asr-head or detected:probe-stub etc.
        # The chosen wording is "picked from probe" (not "auto-detected")
        # so it does not collide with the probe-progress contract on
        # ``dub auto`` that pins the stderr prefix ``auto-detect:`` —
        # the test in tests/test_cli.py asserts that the *prefix* never
        # appears in stdout, but the human route line is now a real
        # stdout line and we do not want the substring overlap to
        # trigger a false positive.
        return f"source language: picked from probe (basis={basis})"
    if basis.startswith("ambiguous:"):
        return f"source language: ambiguous (basis={basis})"
    return f"source language: explicit (basis={basis})"


def _human_route_summary(
    *,
    source_lang: str,
    target_lang: str,
    backend_name: str,
    translate_mode: str,
    translation_provider: str | None,
    project_dir: Path,
    route_basis: str | None,
) -> str:
    """Return a one-line, operator-friendly route summary for the run.

    This is what the operator sees on the success path in addition to the
    machine-oriented ``preflight:`` line. It is intentionally short so a
    first-time operator can read it in one glance and understand:

    * which source/target language pair the run picked,
    * which TTS backend will speak the translated lines,
    * which translation provider is in play (or that translation was skipped),
    * where the project directory lives,
    * how the source language was decided.
    """
    src = _SOURCE_LANG_LABELS.get(source_lang, source_lang)
    tgt = _TARGET_LANG_LABELS.get(target_lang, target_lang)
    backend = _TTS_BACKEND_LABELS.get(backend_name, backend_name)
    if translate_mode == "skip":
        translation = "translation: skipped (using existing project SRT)"
    elif translate_mode == "use-existing":
        translation = "translation: skipped (using external SRT)"
    else:
        provider = translation_provider or "gemini"
        translation = (
            "translation: "
            + _TRANSLATION_PROVIDER_LABELS.get(provider, provider)
        )
    decision = _route_basis_human(route_basis)
    return (
        f"route: {src} -> {tgt} via {backend} ; {translation} ; "
        f"project={project_dir} ; {decision}"
    )


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
    route_basis: str | None = None,
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
        click.echo(_operator_paths_summary("run plan", pdir))
        _validate_run_contract(pdir, cfg)
        click.echo(_run_preflight(pdir, cfg, cfg.defaults.source_lang, route_basis=route_basis))
        click.echo(
            _human_route_summary(
                source_lang=cfg.defaults.source_lang,
                target_lang=cfg.defaults.target_lang,
                backend_name=_tts_backend_for_source(cfg.defaults.source_lang),
                translate_mode=cfg.translation.mode,
                translation_provider=cfg.translation.provider,
                project_dir=pdir,
                route_basis=route_basis,
            )
        )
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


@main.command(name="auto")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--source-lang",
    "source_lang",
    default=None,
    help="Source language route for the one-command workflow (supported: en, ja). "
         "When omitted, `dub auto` auto-detects the source language from the "
         "input video via a short audio head-probe; ambiguous detections fail "
         "fast and ask the operator to re-run with --source-lang en|ja.",
)
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
def auto(video, source_lang, project_dir, config_path, translate_mode, translated_srt, vocal_gain, inst_gain, keep_fulltrack, yes):
    """Run the canonical one-command workflow for English→Chinese or Japanese→Chinese.

    This productized entrypoint resolves the source-language route first,
    then dispatches to the same staged pipeline contract used by the
    explicit `en2zh` and `ja2zh` commands.

    Wave-3 resolution precedence (T3):

    1. Explicit `--source-lang en|ja` (normalized) always wins, even
       when auto-detection would have picked a different route. The
       preflight line prints `route_basis=override:explicit-flag` so
       operators can audit the bypass.
    2. With no flag, `dub auto` runs the auto detector — a 30-second
       audio head-probe transcribed by the repo ASR pipeline and
       classified by character script. The preflight line prints
       `route_basis=detected:<lang>-asr-head`.
    3. Ambiguous detection (no audio track, mixed script, ASR
       unavailable, etc.) fails fast *before* any stage work starts;
       `dub auto` does not silently fall back to
       `cfg.defaults.source_lang`. The error message tells the
       operator to re-run with `--source-lang en|ja`.
    """
    try:
        cfg = load_config(config_path)
        if source_lang is None:
            # Wave 3 (T6): MLX ASR head-probe can run 60-115s with no
            # output otherwise. One stderr line tells the operator the
            # CLI is working and not hung. Preflight echoes the resolved
            # route_basis on its own line right after.
            click.echo(
                "auto-detect: probing 30s audio head for source language...",
                err=True,
            )
        decision = _resolve_auto_route(video, source_lang, cfg)
    except UserError as exc:
        raise click.ClickException(str(exc)) from exc
    if decision.source_lang is None:
        # Ambiguous detection: fail fast with the operator guidance
        # the T1 contract requires. We intentionally do NOT fall
        # back to `cfg.defaults.source_lang` here — that was the
        # old route-aware behavior wave 3 retires.
        raise click.ClickException(
            "Could not confidently detect source language for dub auto "
            f"(basis: {decision.basis}; supported: en, ja). "
            "Re-run with --source-lang en|ja."
        )
    effective_project_dir = project_dir if project_dir is not None else _default_auto_project_dir(video)
    _run_pipeline_command(
        video,
        source_lang=decision.source_lang,
        target_lang="zh",
        project_dir=effective_project_dir,
        config_path=config_path,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
        vocal_gain=vocal_gain,
        inst_gain=inst_gain,
        keep_fulltrack=keep_fulltrack,
        yes=yes,
        route_basis=decision.basis,
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
        raise click.ClickException(
            f"validate failed: project={project_dir} missing state (.dub/state.json)"
        )

    failed_stages = [name for name, st in state.stages.items() if st.status == "failed"]
    if failed_stages:
        raise click.ClickException(
            f"validate failed: project={project_dir} failed_stages={','.join(failed_stages)}"
        )

    final_mp4 = _final_output_path(project_dir)
    if not final_mp4.exists() or final_mp4.stat().st_size == 0:
        raise click.ClickException(
            f"validate failed: project={project_dir} missing final artifact {final_mp4}"
        )

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
    remediation_lines: list[str] = []
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        click.echo(f"{name}: {status} ({detail})")
        if not ok:
            all_ok = False
            hint = _remediation_hint(
                check_name=name,
                check_status="missing",
            )
            if hint:
                remediation_lines.append(hint)

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
    ready_routes: list[str] = []
    blocked_routes: list[str] = []
    backend_to_route = {
        "omnivoice": "dub en2zh",
        "voxcpme": "dub ja2zh",
    }
    for backend_name in builtin_backends():
        readiness = readiness_by_backend[backend_name]
        status = "READY" if readiness.ready else "BLOCKED"
        click.echo(f"  {backend_name}: {status} ({readiness.detail})")
        route_name = backend_to_route.get(backend_name)
        gate_warned = any(gate_status == "warn" for _gate, gate_status, _detail in readiness.checks)
        route_usable = readiness.ready and not gate_warned
        if route_name is not None:
            if route_usable:
                ready_routes.append(route_name)
            else:
                blocked_routes.append(route_name)
                all_ok = False
        for gate, gate_status, detail in readiness.checks:
            click.echo(f"    - {gate}: {gate_status} ({detail})")
            if gate_status != "ok":
                hint = _remediation_hint(
                    check_name=gate,
                    check_status=gate_status,
                    backend_name=backend_name,
                    blocked_route=route_name,
                )
                if hint:
                    remediation_lines.append(hint)

    if all_ok:
        click.echo("doctor ok: ready for `dub auto`, `dub en2zh`, `dub ja2zh`")
        click.echo("doctor next: run `uv run dub auto <VIDEO>` (or `dub en2zh <VIDEO>` / `dub ja2zh <VIDEO>`) to dub end-to-end")
        return

    if ready_routes or blocked_routes:
        route_parts: list[str] = []
        if ready_routes:
            route_parts.append("ready=" + ", ".join(f"`{route}`" for route in ready_routes))
        if blocked_routes:
            route_parts.append("blocked=" + ", ".join(f"`{route}`" for route in blocked_routes))
        click.echo("doctor lanes: " + " ; ".join(route_parts))

    if remediation_lines:
        # De-dup while preserving the order the doctor surfaces gates
        # in (top-level MISSING first, then per-backend BLOCKED gates).
        seen: set[str] = set()
        unique_lines: list[str] = []
        for line in remediation_lines:
            if line in seen:
                continue
            seen.add(line)
            unique_lines.append(line)
        for line in unique_lines:
            click.echo(f"doctor {line}")
        click.echo(
            "doctor next: re-run `uv run dub doctor` after the fix above lands; "
            "full failure list is in the lanes summary above"
        )

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
    click.echo("bootstrap: VoxCPM requires a local server on 127.0.0.1:8808; the canonical entrypoint is this repo's `src/dub/tts_engines/voxcpme/server.py`")
    click.echo("bootstrap: the only required external secret is GOOGLE_API_KEY / GEMINI_API_KEY")
    click.echo("bootstrap: run `dub doctor` to verify every gate before your first real run")
    # The lines above are the explanatory body. The two closing lines
    # are the operator-facing summary: a one-glance "what to do next"
    # and the canonical smoke command. P1A lane B.
    click.echo("bootstrap next: run `uv run dub doctor` to confirm every gate; once it prints `doctor ok: ready for dub auto...`, the canonical smoke is `uv run dub auto <VIDEO>`")
    click.echo("bootstrap first-run: `uv sync --extra all` -> `uv run dub doctor` -> `uv run dub auto <VIDEO>`")


def _remediation_hint(
    *,
    check_name: str,
    check_status: str,
    backend_name: str | None = None,
    blocked_route: str | None = None,
) -> str | None:
    """Return a concrete one-line fix command for a failing ``dub doctor`` gate.

    The hint is what the operator can copy-paste to recover from a single
    MISSING / BLOCKED gate. Returning ``None`` means "no specific hint
    known for this gate" — the caller should fall back to the generic
    ``run ``dub doctor`` for the full report`` pointer.

    ``check_name`` is the gate key (e.g. ``ffmpeg``, ``gemini_api_key``,
    ``interpreter``, ``deps:opencc``, ``service``); ``check_status`` is
    the per-gate status string the readiness object returns (``"ok"``,
    ``"warn"``, ``"missing"``, ``"blocked"``, etc.). ``backend_name`` /
    ``blocked_route`` let the hint include the right backend-specific
    bootstrap command.
    """
    if check_status == "ok":
        return None
    # Top-level (non-TTS) gates
    if check_name == "ffmpeg" or check_name == "ffprobe":
        return "fix: install ffmpeg/ffprobe (macOS: `brew install ffmpeg`; Debian/Ubuntu: `sudo apt-get install -y ffmpeg`)"
    if check_name == "repo_pipeline_scripts":
        return "fix: run `uv sync --extra all` from the repo root to repopulate vendor/pipeline_scripts"
    if check_name == "gemini_api_key":
        return (
            "fix: export GOOGLE_API_KEY (or GEMINI_API_KEY) in your shell, "
            "e.g. `export GOOGLE_API_KEY=...`; `dub doctor` will auto-recover "
            "it from ~/.zshrc / ~/.bashrc on Hermes / CI shells"
        )
    # TTS-backend gates
    if check_name == "interpreter":
        if backend_name == "omnivoice":
            return "fix: run `uv run dub bootstrap-omnivoice` to create the dedicated interpreter and wire paths.omnivoice_python"
        if backend_name == "voxcpme":
            return "fix: run `uv run dub bootstrap-voxcpm` to create the dedicated interpreter and wire paths.voxcpme_python"
        return "fix: run the matching `uv run dub bootstrap-<backend>` to create the dedicated interpreter"
    if check_name.startswith("deps:"):
        mod = check_name.split(":", 1)[1]
        if backend_name == "omnivoice":
            return (
                f"fix: re-run `uv run dub bootstrap-omnivoice`; the {mod} dependency is "
                "missing from the dedicated OmniVoice interpreter"
            )
        if backend_name == "voxcpme":
            return (
                f"fix: re-run `uv run dub bootstrap-voxcpm`; the {mod} dependency is "
                "missing from the dedicated VoxCPM interpreter"
            )
        return f"fix: re-run `dub bootstrap-{backend_name or '<backend>'}`; the {mod} dependency is missing"
    if check_name == "service":
        if backend_name == "voxcpme":
            return (
                "fix: start the local VoxCPM server with "
                "`uv run python -m dub.tts_engines.voxcpme.server --port 8808` "
                "(see docs/operator-runbook.md FR-9)"
            )
        return f"fix: start the {backend_name or '<backend>'} backend service, then re-run `dub doctor`"
    if check_name == "config":
        return f"fix: review your `paths.{backend_name or '<backend>'}_python` in the active config (default: ~/.config/dub/config.yaml)"
    if check_name == "wrapper":
        return f"fix: reinstall the {backend_name or '<backend>'} TTS wrapper via `uv sync --extra all`"
    # Python-import gates under real-backend py:* checks
    if check_name.startswith("py:"):
        mod = check_name.split(":", 1)[1]
        return f"fix: re-run `uv sync --extra all`; the {mod} Python package is missing from the dub venv"
    return None


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

    runtime_import_probes = {
        "omnivoice": ["torch", "omnivoice", "opencc"],
        "voxcpm": ["gradio_client"],
    }
    imports_to_probe = runtime_import_probes.get(backend_name, [])
    if imports_to_probe:
        probe_code = "; ".join(f"import {name}" for name in imports_to_probe)
        try:
            subprocess.run(
                [str(py), "-c", probe_code],
                check=True,
                cwd=str(repo_root),
            )
        except subprocess.CalledProcessError as exc:
            mods = ", ".join(imports_to_probe)
            raise click.ClickException(
                f"bootstrap-{backend_name} installed but runtime import probe failed for: {mods}"
            ) from exc

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
    click.echo("bootstrap-voxcpm: note the local server must still be started separately; use this repo's `src/dub/tts_engines/voxcpme/server.py --port 8808`")
    click.echo(f"bootstrap-voxcpm: next run `uv run dub doctor --config {config_path}`")
