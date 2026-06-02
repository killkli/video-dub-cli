"""stages/stems.py — Stage 1: Demucs stem separation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


class StemsStage(Stage):
    name = "01_stems"

    def is_done(self, project_dir: Path) -> bool:
        vocals = project_dir / "02_stems" / "video.vocals.wav"
        return vocals.exists() and vocals.stat().st_mtime > (project_dir / "01_raw_video" / "video.mp4").stat().st_mtime

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        log_file = project_dir / ".dub" / f"{self.name}.log"
        script = config.paths.skills_dir / "dubbing_stems.py"
        video_mp4 = project_dir / "01_raw_video" / "video.mp4"

        cmd = [
            "python3", str(script),
            str(project_dir),
            "video.mp4",
        ]

        with open(log_file, "w") as fh:
            result = subprocess.run(
                cmd,
                cwd=str(project_dir),
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"exit {result.returncode}"
            return state

        # Discover produced stems
        stems_dir = project_dir / "02_stems"
        artifacts = [p.name for p in stems_dir.glob("video.*.wav")]
        state.artifacts = artifacts
        state.output_dir = "02_stems"
        state.status = "done"
        state.finished_at = now_iso()
        return state