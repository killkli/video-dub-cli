"""stages/asr.py — Stage 2: ASR transcription using qwenasr-mlx."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


class AsrStage(Stage):
    name = "02_asr"

    def is_done(self, project_dir: Path) -> bool:
        srt_path = project_dir / "03_asr" / "video.srt"
        if not srt_path.exists():
            return False
        # Verify non-empty
        text = srt_path.read_text()
        return len(text.strip()) > 50

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        log_file = project_dir / ".dub" / f"{self.name}.log"
        vocals_wav = project_dir / "02_stems" / "video.vocals.wav"
        srt_out = project_dir / "03_asr" / "video.srt"
        cli = config.paths.qwenasr_cli

        cmd = [
            str(cli), "transcribe",
            str(vocals_wav),
            "--output", str(srt_out),
        ]

        with open(log_file, "w") as fh:
            result = subprocess.run(
                cmd,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"exit {result.returncode}"
            return state

        state.artifacts = ["video.srt"]
        state.output_dir = "03_asr"
        state.status = "done"
        state.finished_at = now_iso()
        return state