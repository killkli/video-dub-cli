"""Stage base class and skip-existing interface."""
from __future__ import annotations

import shutil
import subprocess
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
        from datetime import datetime, timezone
        return StageState(status="running", started_at=datetime.now(timezone.utc).isoformat(), attempts=1)

    def mark_done(self, artifacts: list[str] | None = None, output_dir: str | None = None) -> StageState:
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
        return StageState(status="failed", error=error)


def _copy_video(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _video_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def _ensure_silence_wav(path: Path, duration_sec: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration_sec),
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_srt(path: Path, text: str, end_ts: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"1\n00:00:00,000 --> {end_ts}\n{text}\n", encoding="utf-8")


class StemsStage(Stage):
    name = "01_stems"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "02_stems"
        return d.exists() and (d / "vocals.wav").exists() and (d / "instrumental.wav").exists()

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        raw_video = project_dir / "01_raw_video" / "video.mp4"
        duration = _video_duration(raw_video)
        d = project_dir / "02_stems"
        _ensure_silence_wav(d / "vocals.wav", duration)
        _ensure_silence_wav(d / "instrumental.wav", duration)
        return self.mark_done(artifacts=["vocals.wav", "instrumental.wav"], output_dir="02_stems")


# ASRStage is defined canonically in dub.stages.asr. We re-export it here
# so existing import paths (dub.stages.base.ASRStage) keep working while
# the repo converges on a single Stage 2 implementation.
from dub.stages.asr import AsrStage as ASRStage  # noqa: E402,F401


# RefAudioStage is defined canonically in dub.stages.ref_audio (real wire:
# ffmpeg-based extraction via dubbing_extract_ref.py). We re-export it here
# so existing import paths (dub.stages.base.RefAudioStage) keep working.
from dub.stages.ref_audio import RefAudioStage  # noqa: E402,F401

# TtsStage is defined canonically in dub.stages.tts (real wire:
# dubbing_batch_tts.py for en→OmniVoice, dubbing_batch_tts_vox.py for
# ja→VoxCPM). We re-export under both spellings (TTSStage / TtsStage) so
# existing import paths (dub.stages.base.TTSStage) keep working.
from dub.stages.tts import TtsStage  # noqa: E402,F401

# Backwards-compat alias (legacy code referenced TTSStage in some test paths).
TTSStage = TtsStage


# AssembleStage is defined canonically in dub.stages.assemble (real wire:
# time-aligned loudnorm builder + remix + legacy alias/fulltrack handling).
# We re-export it here so existing import paths (dub.stages.base.AssembleStage)
# keep working.
from dub.stages.assemble import AssembleStage  # noqa: E402,F401

from dub.stages.translate import TranslateStage


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
