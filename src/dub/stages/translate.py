"""stages/translate.py — Stage 4: Translate SRT using committed Gemini route."""

from __future__ import annotations

from pathlib import Path

from dub.config import DubConfig
from dub.stages.base import Stage, StageState
from dub.state import now_iso
from dub.translator_gemini import translate_srt_file


class TranslateStage(Stage):
    name = "04_translate"

    def is_done(self, project_dir: Path) -> bool:
        srt_path = project_dir / "05_translated_srt" / "video.zhtw.srt"
        return srt_path.exists() and srt_path.stat().st_size > 50

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        src_srt = project_dir / "03_asr" / "video.srt"
        dst_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"

        if not src_srt.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"Missing ASR SRT: {src_srt}"
            return state

        try:
            translate_srt_file(
                src_srt=src_srt,
                dst_srt=dst_srt,
                source_lang=config.defaults.source_lang,
                target_lang=config.defaults.target_lang,
                cfg=config.translation,
            )
        except Exception as e:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = str(e)
            return state

        state.artifacts = ["video.zhtw.srt"]
        state.output_dir = "05_translated_srt"
        state.status = "done"
        state.finished_at = now_iso()
        return state
