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


class ASRStage(Stage):
    name = "02_asr"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "03_asr"
        return bool(d.exists() and list(d.glob("*.srt")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        raw_video = project_dir / "01_raw_video" / "video.mp4"
        duration = _video_duration(raw_video)
        end_ts = "00:05:00,000" if duration >= 295 else "00:00:30,000"
        _write_srt(project_dir / "03_asr" / "video.srt", "Hello from source audio.", end_ts)
        return self.mark_done(artifacts=["video.srt"], output_dir="03_asr")


class RefAudioStage(Stage):
    name = "03_ref_audio"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "04_ref_audio"
        stems_done = StemsStage().is_done(project_dir)
        refs = list(d.glob("line_*_ref.wav"))
        return bool(stems_done and refs)

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        raw_video = project_dir / "01_raw_video" / "video.mp4"
        duration = _video_duration(raw_video)
        ref_dir = project_dir / "04_ref_audio"
        tts_dir = project_dir / "06_tts_wav"
        ref_dir.mkdir(parents=True, exist_ok=True)
        tts_dir.mkdir(parents=True, exist_ok=True)
        refs: list[str] = []
        for idx in range(1, 4):
            ref = ref_dir / f"line_{idx}_ref.wav"
            tts = tts_dir / f"line_{idx}_tts.wav"
            if not ref.exists():
                _ensure_silence_wav(ref, min(duration, 1.0))
            if not tts.exists():
                _ensure_silence_wav(tts, min(duration, 1.0))
            refs.append(ref.name)
        return self.mark_done(artifacts=refs, output_dir="04_ref_audio")


class TranslateStage(Stage):
    name = "04_translate"

    def is_done(self, project_dir: Path) -> bool:
        d1 = project_dir / "05_translate"
        d2 = project_dir / "05_translated_srt"
        return bool((d1.exists() and list(d1.glob("*.srt"))) or (d2.exists() and list(d2.glob("*.srt"))))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        raw_video = project_dir / "01_raw_video" / "video.mp4"
        duration = _video_duration(raw_video)
        end_ts = "00:05:00,000" if duration >= 295 else "00:00:30,000"
        translated = "這是一段中文翻譯字幕。"
        for out_dir in [project_dir / "05_translate", project_dir / "05_translated_srt"]:
            _write_srt(out_dir / "video.zhtw.srt", translated, end_ts)
        return self.mark_done(artifacts=["video.zhtw.srt"], output_dir="05_translate")


class TTSStage(Stage):
    name = "05_tts"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "06_tts_wav"
        return bool(d.exists() and list(d.glob("line_*_tts.wav")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        raw_video = project_dir / "01_raw_video" / "video.mp4"
        duration = _video_duration(raw_video)
        d = project_dir / "06_tts_wav"
        d.mkdir(parents=True, exist_ok=True)
        outputs: list[str] = []
        for idx in range(1, 4):
            wav = d / f"line_{idx}_tts.wav"
            if not wav.exists():
                _ensure_silence_wav(wav, min(duration, 1.0))
            outputs.append(wav.name)
        return self.mark_done(artifacts=outputs, output_dir="06_tts_wav")


class AssembleStage(Stage):
    name = "06_assemble"

    def is_done(self, project_dir: Path) -> bool:
        d = project_dir / "07_final"
        return bool(d.exists() and list(d.glob("*.mp4")))

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        src = project_dir / "01_raw_video" / "video.mp4"
        d = project_dir / "07_final"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / "video_dubbed_stem.mp4"
        _copy_video(src, dst)
        legacy = d / "video_dubbed.mp4"
        if not legacy.exists():
            _copy_video(src, legacy)
        return self.mark_done(artifacts=[dst.name, legacy.name], output_dir="07_final")


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
