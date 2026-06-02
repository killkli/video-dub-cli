"""stages/tts.py — Stage 5: per-segment TTS with source-lang routing.

Real wire: invokes one of two scripts (under config.paths.skills_dir):

  en  → dubbing_batch_tts.py    (OmniVoice, MPS)
  ja  → dubbing_batch_tts_vox.py (VoxCPM, gradio_client → local server)
  *   → dubbing_batch_tts.py    (default to OmniVoice)

Contract (frozen by P3-T0 orchestration gate, 2026-06-02):

  Inputs
    05_translated_srt/video.zhtw.srt  — zh-TW translation, fed as ``--zh-srt``
    03_asr/video.srt                  — original language ASR, fed as the
                                        ref_text source. Script flag differs
                                        by route: ``--en-srt`` (OmniVoice)
                                        vs ``--ja-srt`` (VoxCPM).
    04_ref_audio/line_<i>_ref.wav     — per-cue ref audio (sliced from
                                        01_raw_video/video.mp4 by
                                        dubbing_extract_ref.py).

  Output
    06_tts_wav/line_<i>_tts.wav       — one WAV per ASR cue, indexed by
                                        SRT cue number.

  In-script pairing (the scripts' job, not ours)
    ref_text = en/ja original cue text (逐字稿)
    text     = zh-TW translation (already simplified by opencc t2s inside
                                       the script)
    ref_audio = 04_ref_audio/line_<i>_ref.wav

is_done() is strict: every cue in 03_asr/video.srt (cue count = N) must
have BOTH a ref wav in 04_ref_audio/ AND a tts wav in 06_tts_wav/ of
non-trivial size (> 1000 bytes — matches the VoxCPM script's own
skip-existing threshold, so we don't accept zero-byte placeholders).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from dub.config import DubConfig
from dub.state import now_iso
from dub.stages.base import Stage, StageState


# Reuse the SRT-cue counter from ref_audio. The two stages need to agree
# on "how many cues are there" for is_done to be a stable invariant.
from dub.stages.ref_audio import _count_srt_cues  # noqa: E402

# VoxCPM script's own skip threshold. We mirror it here so is_done treats
# a 200-byte placeholder the same way the script would on a re-run.
_TTS_MIN_BYTES = 1000

# Routes: source_lang → (script, source_srt_flag, needs_project_dir)
#
# OmniVoice (en) uses --en-srt because the script was originally written
# for an English source. VoxCPM (ja) uses --ja-srt and additionally
# requires --project-dir for its own path resolution / defaults. Any other
# source_lang defaults to OmniVoice for safety.
_ROUTES: dict[str, tuple[str, str, bool]] = {
    "en": ("dubbing_batch_tts.py", "--en-srt", False),
    "ja": ("dubbing_batch_tts_vox.py", "--ja-srt", True),
}


def _list_tts_wavs(tts_dir: Path) -> list[Path]:
    if not tts_dir.exists():
        return []
    return sorted(p for p in tts_dir.glob("line_*_tts.wav") if p.stat().st_size > _TTS_MIN_BYTES)


class TtsStage(Stage):
    """Stage 5: per-segment TTS, routing by config.defaults.source_lang."""

    name = "05_tts"

    def is_done(self, project_dir: Path) -> bool:
        """True iff 03_asr/video.srt, every cue 1..N has a ref wav in
        04_ref_audio/, AND every cue 1..N has a non-trivial tts wav in
        06_tts_wav/.

        We cross-check against the ASR SRT (not the translated SRT) because
        ref_audio was sliced from the ASR cues and downstream assemble
        aligns audio against the ASR timeline. A successful TTS that drifts
        from the ASR cue count is a partial run we refuse to declare done.
        """
        srt_path = project_dir / "03_asr" / "video.srt"
        if not srt_path.exists():
            return False
        expected = _count_srt_cues(srt_path)
        if expected == 0:
            return False

        ref_dir = project_dir / "04_ref_audio"
        for i in range(1, expected + 1):
            if not (ref_dir / f"line_{i}_ref.wav").exists():
                return False

        tts_dir = project_dir / "06_tts_wav"
        for i in range(1, expected + 1):
            wav = tts_dir / f"line_{i}_tts.wav"
            if not wav.exists() or wav.stat().st_size <= _TTS_MIN_BYTES:
                return False
        return True

    def _resolve_route(self, source_lang: str, skills_dir: Path) -> tuple[Path, str, bool]:
        """Return (script_path, source_srt_flag, needs_project_dir) for the
        given source_lang.

        Unknown source_langs fall back to the OmniVoice (en) route so the
        pipeline still attempts something rather than failing closed.
        """
        script_name, src_flag, needs_project_dir = _ROUTES.get(source_lang, _ROUTES["en"])
        return skills_dir / script_name, src_flag, needs_project_dir

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(
            status="running", started_at=now_iso(), attempts=1
        )

        zh_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"
        asr_srt = project_dir / "03_asr" / "video.srt"
        ref_dir = project_dir / "04_ref_audio"
        tts_dir = project_dir / "06_tts_wav"
        log_file = project_dir / ".dub" / f"{self.name}.log"

        # Pre-flight: every input must exist before we shell out, otherwise
        # the per-segment script will fail mid-way through and leave a
        # half-finished 06_tts_wav/ behind (which then trips is_done).
        for label, path in (("zh SRT", zh_srt), ("ASR SRT", asr_srt), ("ref dir", ref_dir)):
            if not path.exists():
                state.status = "failed"
                state.finished_at = now_iso()
                state.error = f"{label} missing: {path}"
                return state

        tts_dir.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        script, src_flag, needs_project_dir = self._resolve_route(
            config.defaults.source_lang, config.paths.skills_dir
        )
        if not script.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"TTS script not found: {script}"
            return state

        # The two scripts share this flag set. The interpreter matters:
        # OmniVoice must run under its own venv (torch + omnivoice pkg);
        # VoxCPM runs under the project venv (gradio_client + opencc).
        # We default to omnivoice_python for both — the VoxCPM script
        # doesn't import torch, so a python with gradio_client also works
        # fine, and pinning one interpreter keeps the stage deterministic.
        py = config.paths.omnivoice_python
        cmd = [str(py), str(script)]
        if needs_project_dir:
            cmd.extend(["--project-dir", str(project_dir)])
        cmd.extend([
            "--zh-srt", str(zh_srt),
            src_flag, str(asr_srt),
            "--ref-dir", str(ref_dir),
            "--out-dir", str(tts_dir),
        ])

        with open(log_file, "w", encoding="utf-8") as log_fh:
            result = subprocess.run(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = (
                f"{script.name} exited with code {result.returncode}; see {log_file}"
            )
            return state

        # Post-flight: the script may exit 0 after partial success. Verify
        # every ASR cue has a non-trivial tts wav, otherwise the pipeline
        # is in a half-done state and downstream assemble will misalign.
        expected = _count_srt_cues(asr_srt)
        produced = [p.name for p in _list_tts_wavs(tts_dir)]
        missing = [
            f"line_{i}_tts.wav"
            for i in range(1, expected + 1)
            if not (tts_dir / f"line_{i}_tts.wav").exists()
            or (tts_dir / f"line_{i}_tts.wav").stat().st_size <= _TTS_MIN_BYTES
        ]
        if missing:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = (
                f"{script.name} produced {len(produced)}/{expected} tts wavs; "
                f"missing or too small: {', '.join(missing)}; see {log_file}"
            )
            return state

        state.artifacts = sorted(p.name for p in tts_dir.glob("line_*_tts.wav"))
        state.output_dir = "06_tts_wav"
        state.status = "done"
        state.finished_at = now_iso()
        return state


__all__ = ["TtsStage"]
