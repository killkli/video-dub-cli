"""Stage base class and skip-existing interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from dub.config import DubConfig
from dub.state import StageState


class Stage(ABC):
    """Abstract base for all pipeline stages."""

    name: str  # e.g. "01_stems"

    @abstractmethod
    def is_done(self, project_dir: Path) -> bool:
        """Return True if this stage's artifacts already exist (skip)."""

    @abstractmethod
    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        """Execute the stage, returning the new StageState."""

    def mark_running(self) -> StageState:
        """Helper to create a 'running' StageState."""
        from datetime import datetime, timezone
        return StageState(status="running", started_at=datetime.now(timezone.utc).isoformat(), attempts=1)

    def mark_done(self, artifacts: list[str] | None = None, output_dir: str | None = None) -> StageState:
        """Helper to create a 'done' StageState."""
        from datetime import datetime, timezone
        return StageState(
            status="done",
            started_at=None,
            finished_at=datetime.now(timezone.utc).isoformat(),
            attempts=1,
            artifacts=artifacts or [],
            output_dir=output_dir,
        )

    def mark_failed(self, error: str) -> StageState:
        """Helper to create a 'failed' StageState."""
        from datetime import datetime, timezone
        return StageState(
            status="failed",
            error=error,
        )


# ─── Concrete stage stubs ────────────────────────────────────────────────────


class StemsStage(Stage):
    name = "01_stems"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "02_stems"
        # Both vocal + instrumental must exist to consider stems done
        return (
            d.exists()
            and (d / "vocals.wav").exists()
            and (d / "instrumental.wav").exists()
        )

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub — T4 implements actual separation
        return self.mark_done(artifacts=["vocals.wav", "instrumental.wav"], output_dir="02_stems")


class ASRStage(Stage):
    name = "02_asr"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "03_asr"
        return bool(d.exists() and list(d.glob("*.srt")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub
        return self.mark_done(artifacts=["video.srt"], output_dir="03_asr")


class RefAudioStage(Stage):
    name = "03_ref_audio"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "04_ref_audio"
        # Ref audio only makes sense if stems are done (vocal source exists)
        stems_done = StemsStage().is_done(project_dir)
        return bool(stems_done and d.exists() and list(d.glob("line_*_ref.wav")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub
        return self.mark_done(artifacts=[], output_dir="04_ref_audio")


class TranslateStage(Stage):
    name = "04_translate"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "05_translated_srt"
        return bool(d.exists() and list(d.glob("*.srt")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub
        return self.mark_done(artifacts=["video.zhtw.srt"], output_dir="05_translated_srt")


class TTSStage(Stage):
    name = "05_tts"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "06_tts_wav"
        # At least one line_*_tts.wav must exist
        return bool(d.exists() and list(d.glob("line_*_tts.wav")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub
        return self.mark_done(artifacts=[], output_dir="06_tts_wav")


class AssembleStage(Stage):
    name = "06_assemble"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "07_final"
        return bool(d.exists() and list(d.glob("*.mp4")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        # stub
        return self.mark_done(artifacts=["video_dubbed.mp4"], output_dir="07_final")


STAGE_REGISTRY: dict[str, Stage] = {
    "01_stems": StemsStage(),
    "02_asr": ASRStage(),
    "03_ref_audio": RefAudioStage(),
    "04_translate": TranslateStage(),
    "05_tts": TTSStage(),
    "06_assemble": AssembleStage(),
}


def get_stage(name: str) -> Stage:
    return STAGE_REGISTRY[name]