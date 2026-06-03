from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SubtitleConfig:
    min_segment_duration: float = 0.3
    max_segment_duration: float = 10.0
    output_format: str = "srt"  # "srt" | "vtt"


@dataclass(slots=True)
class TranscriptionRequest:
    input_path: Path
    output_format: str = "txt"
    language: str | None = None
    prompt: str | None = None
    diarize: bool = False
    num_speakers: int | None = None
    subtitle_config: SubtitleConfig | None = None


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    output_format: str
    backend_name: str
    segments: list[Segment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
