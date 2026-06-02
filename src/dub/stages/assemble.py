"""stages/assemble.py — Stage 6: Assemble final dubbed video from TTS + stems."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


class AssembleStage(Stage):
    name = "06_assemble"

    def is_done(self, project_dir: Path) -> bool:
        return (project_dir / "07_final" / "video_dubbed_stem.mp4").exists()

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        log_file = project_dir / ".dub" / f"{self.name}.log"
        skills_dir = config.paths.skills_dir

        # ── Step 1: loudnorm-normalize TTS mix ─────────────────────────────────
        tts_normalized = project_dir / "06_tts_wav" / "tts_normalized.wav"
        ref_wavs = sorted((project_dir / "06_tts_wav").glob("line_*_tts.wav"))
        if ref_wavs and not tts_normalized.exists():
            # Concatenate all line tts files, then loudnorm
            concat_list = project_dir / "06_tts_wav" / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{w}'" for w in ref_wavs)
            )
            raw_mix = project_dir / "06_tts_wav" / "tts_raw_mix.wav"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-acodec", "pcm_s16le", str(raw_mix),
            ], check=True)
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(raw_mix),
                "-af", "loudnorm=I=-16:TP=-1:LRA=11",
                "-acodec", "pcm_s16le", str(tts_normalized),
            ], check=True)

        # ── Step 2: stem-preserving remix ──────────────────────────────────────
        remix_script = skills_dir / "dubbing_remix.py"
        remix_log = project_dir / ".dub" / "06_assemble_remix.log"
        out_stem = project_dir / "07_final" / "video_dubbed_stem.mp4"

        remix_cmd = [
            "python3", str(remix_script),
            "--project-dir", str(project_dir),
            "--vocal-mix", str(tts_normalized),
            "--output", str(out_stem),
            "--vocal-gain", str(config.defaults.vocal_gain),
            "--inst-gain", str(config.defaults.inst_gain),
        ]

        with open(remix_log, "w") as fh:
            result = subprocess.run(
                remix_cmd,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"remix exit {result.returncode}"
            return state

        artifacts = ["video_dubbed_stem.mp4"]

        # ── Step 3: optionally assemble loudnorm version ───────────────────────
        if config.defaults.keep_fulltrack:
            loudnorm_script = skills_dir / "dubbing_assemble_loudnorm.py"
            loudnorm_log = project_dir / ".dub" / "06_assemble_loudnorm.log"
            out_fulltrack = project_dir / "07_final" / "video_dubbed_fulltrack.mp4"

            ln_cmd = [
                "python3", str(loudnorm_script),
                "--video", str(project_dir / "01_raw_video" / "video.mp4"),
                "--zh-srt", str(project_dir / "05_translated_srt" / "video.zhtw.srt"),
                "--tts-dir", str(project_dir / "06_tts_wav"),
                "--output", str(out_fulltrack),
            ]
            with open(loudnorm_log, "w") as fh:
                subprocess.run(ln_cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
            artifacts.append("video_dubbed_fulltrack.mp4")

        state.artifacts = artifacts
        state.output_dir = "07_final"
        state.status = "done"
        state.finished_at = now_iso()
        return state