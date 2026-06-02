"""stages/ref_audio.py — Stage 3: Extract per-segment reference audio from video+SRT."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


class RefAudioStage(Stage):
    name = "03_ref_audio"

    def is_done(self, project_dir: Path) -> bool:
        first_ref = project_dir / "04_ref_audio" / "line_1_ref.wav"
        return first_ref.exists()

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        log_file = project_dir / ".dub" / f"{self.name}.log"
        script = config.paths.skills_dir / "dubbing_extract_ref.py"
        video_mp4 = project_dir / "01_raw_video" / "video.mp4"
        srt = project_dir / "03_asr" / "video.srt"
        out_dir = project_dir / "04_ref_audio"

        cmd = [
            "python3", str(script),
            str(video_mp4),
            str(srt),
            str(out_dir) + "/",
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

        artifacts = [p.name for p in out_dir.glob("line_*_ref.wav")]
        state.artifacts = sorted(artifacts)
        state.output_dir = "04_ref_audio"
        state.status = "done"
        state.finished_at = now_iso()
        return state