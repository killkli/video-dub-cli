"""stages/translate.py — Stage 4: Translate SRT using subtitle_translation.py."""

from __future__ import annotations

from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

from dub.stages.base import Stage, StageState
from dub.config import DubConfig
from dub.state import now_iso


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

        script_path = config.paths.translation_skill
        spec = spec_from_file_location("subtitle_translation", script_path)
        if spec is None or spec.loader is None:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"Could not load {script_path}"
            return state

        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        translate_fn = getattr(mod, "translate_srt", None) or getattr(mod, "main", None)
        if translate_fn is None:
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"{script_path} has no translate_srt or main function"
            return state

        try:
            translate_fn(str(src_srt), str(dst_srt))
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
