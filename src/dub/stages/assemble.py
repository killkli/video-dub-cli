"""stages/assemble.py — Stage 6: assemble final dubbed video from TTS + stems.

Real wire via repo-owned scripts under `vendor/pipeline_scripts/`
(P3-T4 contract, frozen by the T0 orchestration gate 2026-06-02):

  Inputs
    06_tts_wav/line_<i>_tts.wav  — per-cue TTS wavs from Stage 5
    02_stems/{video_file}.instrumental.wav — non-vocal bed, consumed by remix
    01_raw_video/video.mp4       — mux source

  Pipeline
    1) dubbing_assemble_loudnorm.py (time-aligned fulltrack builder)
         in:  --video <video.mp4> --zh-srt <video.zhtw.srt> --tts-dir <06_tts_wav>
              --save-normalized-wav <06_tts_wav/tts_normalized.wav>
              --output <fulltrack.mp4 OR throwaway temp mp4>
         out: 06_tts_wav/tts_normalized.wav
              + time-aligned fulltrack mp4 when keep_fulltrack=True
    2) dubbing_remix.py  (stem-preserving remix, replaces vocals)
         in:  --project-dir <p> --vocal-mix <tts_normalized.wav>
              --vocal-gain <db> --inst-gain <db>
              (remix internally finds 02_stems/<video_file>.instrumental.wav)
         out: 07_final/video_dubbed_stem.mp4
    3) Legacy alias (compatibility shim)
         cp(video_dubbed_stem.mp4 → video_dubbed.mp4)
    4) keep_fulltrack=True only
         retain the fulltrack mp4 emitted in step 1 as
         07_final/video_dubbed_fulltrack.mp4

  Failure semantics
    - remix returns non-zero OR exits 0 without writing the stem mp4 → stage
      fails. No mp4 left behind in 07_final/ as a half-truth.
    - If the time-aligned fulltrack builder fails, the stage fails (it is the
      source of the canonical tts_normalized.wav used by remix).
    - Pre-flight errors (missing source video, no tts wavs, missing scripts)
      fail fast with a clear error message.

  is_done()
    Canonical artifact: 07_final/video_dubbed_stem.mp4. Returns True iff
    that file exists with non-zero size. The legacy `video_dubbed.mp4`
    alias is not checked separately (it's a copy of the stem; if the stem
    exists, the alias is regenerated next run anyway).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from dub.config import DubConfig
from dub.state import now_iso
from dub.stages.base import Stage, StageState


# Minimum size for any produced mp4 to be considered real. A failed remix
# that wrote a 200-byte stub should not be accepted as "done" — this matches
# the >=1000 byte byte-size gate T2/T3 use for ref/tts wavs.
_MIN_MP4_BYTES = 1000


class AssembleStage(Stage):
    name = "06_assemble"

    def is_done(self, project_dir: Path) -> bool:
        """True iff 07_final/video_dubbed_stem.mp4 exists with non-trivial size.

        We check only the canonical stem output. The legacy
        `video_dubbed.mp4` alias is a copy of the stem; if the stem is
        there, the alias is regenerated next run.
        """
        stem = project_dir / "07_final" / "video_dubbed_stem.mp4"
        if not stem.exists():
            return False
        return stem.stat().st_size > _MIN_MP4_BYTES

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(
            status="running",
            started_at=now_iso(),
            attempts=1,
        )

        final_dir = project_dir / "07_final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / ".dub").mkdir(parents=True, exist_ok=True)

        # ── Pre-flight: every input the scripts need must be on disk ──────────
        source_video = project_dir / "01_raw_video" / "video.mp4"
        if not source_video.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"source video missing: {source_video}"
            return state

        tts_dir = project_dir / "06_tts_wav"
        tts_wavs = sorted(tts_dir.glob("line_*_tts.wav"))
        if not tts_wavs:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"no TTS wavs in {tts_dir} (Stage 5 did not produce output)"
            return state

        # ── Step 1: build time-aligned tts_normalized.wav via canonical
        #           dubbing_assemble_loudnorm.py ───────────────────────────────
        tts_normalized = tts_dir / "tts_normalized.wav"
        zh_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"
        if not zh_srt.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"translated zh SRT missing: {zh_srt}"
            return state

        loudnorm_script = config.paths.skills_dir / "dubbing_assemble_loudnorm.py"
        if not loudnorm_script.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"loudnorm script not found: {loudnorm_script}"
            return state

        step1_log = project_dir / ".dub" / f"{self.name}_step1_tts.log"
        out_fulltrack = final_dir / "video_dubbed_fulltrack.mp4"

        need_builder = (not tts_normalized.exists()) or (
            config.defaults.keep_fulltrack
            and (not out_fulltrack.exists() or out_fulltrack.stat().st_size <= _MIN_MP4_BYTES)
        )

        if need_builder:
            temp_fulltrack = None
            fulltrack_output = out_fulltrack
            if not config.defaults.keep_fulltrack:
                temp_fulltrack = Path(tempfile.mkstemp(prefix="vdub_fulltrack_", suffix=".mp4", dir=str(project_dir / ".dub"))[1])
                fulltrack_output = temp_fulltrack

            loudnorm_cmd = [
                "python3", str(loudnorm_script),
                "--video", str(source_video),
                "--zh-srt", str(zh_srt),
                "--tts-dir", str(tts_dir),
                "--output", str(fulltrack_output),
                "--save-normalized-wav", str(tts_normalized),
            ]
            with open(step1_log, "w") as log_fh:
                r1 = subprocess.run(
                    loudnorm_cmd,
                    stdout=log_fh, stderr=subprocess.STDOUT, check=False,
                )
                if r1.returncode != 0:
                    state.status = "failed"
                    state.finished_at = now_iso()
                    state.error = f"time-aligned loudnorm builder exit {r1.returncode}; see {step1_log}"
                    return state

            if not tts_normalized.exists() or tts_normalized.stat().st_size <= _MIN_MP4_BYTES:
                state.status = "failed"
                state.finished_at = now_iso()
                state.error = f"time-aligned loudnorm builder produced no/empty normalized wav: {tts_normalized}"
                return state

            if config.defaults.keep_fulltrack:
                if not out_fulltrack.exists() or out_fulltrack.stat().st_size <= _MIN_MP4_BYTES:
                    state.status = "failed"
                    state.finished_at = now_iso()
                    state.error = f"time-aligned loudnorm builder exited 0 but {out_fulltrack} missing or too small; see {step1_log}"
                    return state
            elif temp_fulltrack is not None and temp_fulltrack.exists():
                temp_fulltrack.unlink()

        # ── Step 2: dubbing_remix.py → video_dubbed_stem.mp4 ──────────────────
        remix_script = config.paths.skills_dir / "dubbing_remix.py"
        if not remix_script.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"remix script not found: {remix_script}"
            return state

        stems_dir = project_dir / "02_stems"
        canonical_inst = stems_dir / "instrumental.wav"
        remix_compat_inst = stems_dir / "video.mp4.instrumental.wav"
        if canonical_inst.exists() and not remix_compat_inst.exists():
            shutil.copy2(canonical_inst, remix_compat_inst)

        out_stem = final_dir / "video_dubbed_stem.mp4"
        # Make sure a stale file from a previous run doesn't get re-detected
        # if remix silently fails to overwrite.
        if out_stem.exists():
            out_stem.unlink()

        remix_log = project_dir / ".dub" / f"{self.name}_remix.log"
        remix_cmd = [
            "python3", str(remix_script),
            "--project-dir", str(project_dir),
            "--vocal-mix", str(tts_normalized),
            "--output", str(out_stem),
            "--vocal-gain", str(config.defaults.vocal_gain),
            "--inst-gain", str(config.defaults.inst_gain),
        ]
        with open(remix_log, "w") as log_fh:
            result = subprocess.run(
                remix_cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"remix exit {result.returncode}; see {remix_log}"
            return state

        if not out_stem.exists() or out_stem.stat().st_size <= _MIN_MP4_BYTES:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"remix exited 0 but {out_stem} missing or too small; see {remix_log}"
            return state

        # ── Step 3: legacy alias (compatibility shim) ─────────────────────────
        legacy = final_dir / "video_dubbed.mp4"
        if not legacy.exists() or legacy.stat().st_size <= _MIN_MP4_BYTES:
            shutil.copy2(out_stem, legacy)

        artifacts = [out_stem.name, legacy.name]
        if config.defaults.keep_fulltrack:
            artifacts.append(out_fulltrack.name)

        state.artifacts = artifacts
        state.output_dir = "07_final"
        state.status = "done"
        state.finished_at = now_iso()
        return state


__all__ = ["AssembleStage"]
