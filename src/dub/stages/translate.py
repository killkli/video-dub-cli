"""stages/translate.py — Stage 4: Translate SRT using committed Gemini route."""

from __future__ import annotations

import shutil
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
        primary_srt = project_dir / "05_translate" / "video.zhtw.srt"
        mode = config.translation.mode
        existing_srt = config.translation.translated_srt

        if not src_srt.exists():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"Missing ASR SRT: {src_srt}"
            return state

        dst_srt.parent.mkdir(parents=True, exist_ok=True)
        primary_srt.parent.mkdir(parents=True, exist_ok=True)

        if mode == "skip":
            state.status = "skipped"
            state.output_dir = "05_translated_srt"
            state.finished_at = now_iso()
            return state

        if mode == "use-existing":
            if existing_srt is None:
                state.status = "failed"
                state.finished_at = now_iso()
                state.error = "translate-mode=use-existing requires --translated-srt"
                return state
            if not existing_srt.exists():
                state.status = "failed"
                state.finished_at = now_iso()
                state.error = f"Translated SRT not found: {existing_srt}"
                return state
            shutil.copy2(existing_srt, dst_srt)
            if primary_srt.resolve() != dst_srt.resolve():
                shutil.copy2(dst_srt, primary_srt)
            state.artifacts = ["video.zhtw.srt"]
            state.output_dir = "05_translated_srt"
            state.status = "done"
            state.finished_at = now_iso()
            return state

        try:
            translate_srt_file(
                src_srt=src_srt,
                dst_srt=dst_srt,
                source_lang=config.defaults.source_lang,
                target_lang=config.defaults.target_lang,
                cfg=config.translation,
            )
            if primary_srt.resolve() != dst_srt.resolve():
                shutil.copy2(dst_srt, primary_srt)
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
