"""stages/asr.py — Stage 2: ASR transcription using repo-owned qwenasr_mlx_cli."""

from __future__ import annotations

from pathlib import Path

from dub.config import DubConfig
from dub.state import now_iso
from dub.stages.base import Stage, StageState
from qwenasr_mlx_cli.core.exceptions import ASRProcessingError, BackendUnavailableError, InputValidationError
from qwenasr_mlx_cli.core.types import SubtitleConfig
from qwenasr_mlx_cli.pipelines.transcribe import run_transcription


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

        srt_out.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        subtitle_config = SubtitleConfig(output_format="srt")
        try:
            rendered = run_transcription(
                input_path=input_video,
                backend_name="mlx",
                output_format="srt",
                language=config.defaults.source_lang or None,
                prompt=None,
                subtitle_config=subtitle_config,
                convert_simplified_to_traditional=False,
            )
        except (BackendUnavailableError, InputValidationError, ASRProcessingError, NotImplementedError) as exc:
            log_file.write_text(f"ERROR: {exc}\n", encoding="utf-8")
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"repo ASR pipeline failed: {exc}; see {log_file}"
            return state

        srt_out.write_text(rendered, encoding="utf-8")
        log_file.write_text("repo ASR pipeline completed\n", encoding="utf-8")

        if not srt_out.exists() or not srt_out.read_text(encoding="utf-8").strip():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"repo ASR pipeline produced empty SRT; see {log_file}"
            return state

        state.artifacts = ["video.srt"]
        state.output_dir = "03_asr"
        state.status = "done"
        state.finished_at = now_iso()
        return state