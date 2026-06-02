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
        return srt_path.exists()

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        input_video = project_dir / "01_raw_video" / "video.mp4"
        srt_out = project_dir / "03_asr" / "video.srt"
        log_file = project_dir / ".dub" / f"{self.name}.log"
        cli = config.paths.qwenasr_cli

        srt_out.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(cli),
            "transcribe",
            str(input_video),
            "--output-format",
            "srt",
        ]
        if config.defaults.source_lang:
            cmd += ["--language", config.defaults.source_lang]

        with open(srt_out, "w", encoding="utf-8") as out_fh, open(log_file, "w", encoding="utf-8") as log_fh:
            result = subprocess.run(
                cmd,
                stdout=out_fh,
                stderr=log_fh,
                text=True,
                check=False,
            )

        if result.returncode != 0:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"qwenasr-mlx exited with code {result.returncode}; see {log_file}"
            return state

        if not srt_out.exists() or not srt_out.read_text(encoding="utf-8").strip():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"qwenasr-mlx produced empty SRT; see {log_file}"
            return state

        state.artifacts = ["video.srt"]
        state.output_dir = "03_asr"
        state.status = "done"
        state.finished_at = now_iso()
        return state