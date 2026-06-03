"""Voice Activity Detection (VAD) segmentation using Silero VAD.

This module provides segment_by_vad() which:
1. Loads audio (16 kHz mono) from the given path
2. Runs Silero VAD to detect speech regions with real timestamps
3. Filters by min/max segment duration
4. Per speech region: extracts the audio chunk and runs MLX transcription
   to attribute text to that time range
5. Returns list[Segment] with real start/end timestamps

This is the "Option D" path from the subtitle-timestamp plan — the only way
to get real subtitle timestamps with qwen3-asr-mlx, which doesn't expose
word/segment timing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from qwenasr_mlx_cli.core.exceptions import ASRProcessingError
from qwenasr_mlx_cli.core.types import Segment, SubtitleConfig
from qwenasr_mlx_cli.backends.registry import BackendRegistry


def _normalize_audio_for_vad(audio_path: Path) -> Path | None:
    """Return a temp 16 kHz mono WAV path when normalization is required.

    For non-WAV media and WAV files that are not already 16 kHz mono, use
    pydub/ffmpeg to decode and export a real PCM WAV. This avoids corrupting the
    audio by reinterpreting float32 buffers as 16-bit PCM bytes.
    """
    try:
        import torchaudio
    except Exception as exc:  # pragma: no cover
        raise ASRProcessingError(
            f"torch/torchaudio are required for subtitle output. Install with `pip install torch torchaudio`. {exc}"
        ) from exc

    try:
        info = torchaudio.info(str(audio_path))
        needs_normalization = (
            audio_path.suffix.lower() != ".wav"
            or info.sample_rate != 16000
            or info.num_channels != 1
        )
    except Exception:
        needs_normalization = True

    if not needs_normalization:
        return None

    try:
        import pydub
    except ImportError as exc:
        raise ASRProcessingError(
            "pydub is required for subtitle output on non-WAV files. Install with `pip install pydub`."
        ) from exc

    audio = pydub.AudioSegment.from_file(str(audio_path))
    audio = audio.set_frame_rate(16000).set_channels(1)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav_path = Path(tmp.name)
    audio.export(str(tmp_wav_path), format="wav")
    return tmp_wav_path


def segment_by_vad(
    audio_path: Path,
    transcription_text: str,
    config: SubtitleConfig,
) -> list[Segment]:
    """Detect speech segments via Silero VAD and transcribe each segment.

    Args:
        audio_path: Path to a 16 kHz mono WAV file (or any format supported by pydub).
        transcription_text: Full audio transcription text (used as metadata; each
            VAD segment is re-transcribed independently).
        config: SubtitleConfig with min/max segment duration and output_format.

    Returns:
        List of Segment objects with real start/end timestamps and transcribed text.
    """
    try:
        from silero_vad import get_speech_timestamps, read_audio, load_silero_vad  # noqa: F401
        import torch  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise ASRProcessingError(
            f"silero-vad and torch/torchaudio are required for subtitle output. "
            f"Install with `pip install silero-vad torch torchaudio`. {exc}"
        ) from exc

    # Load Silero VAD model (required by silero-vad >= 0.4)
    model = load_silero_vad()

    # Load audio (Silero expects 16 kHz mono WAV; if not, convert via pydub → temp)
    tmp_wav_path: Path | None = None
    audio_for_vad_path = str(audio_path)

    try:
        tmp_wav_path = _normalize_audio_for_vad(audio_path)
        if tmp_wav_path is not None:
            audio_for_vad_path = str(tmp_wav_path)

        # Run Silero VAD
        wav = read_audio(audio_for_vad_path, sampling_rate=16000)
        speech_timestamps = get_speech_timestamps(
            wav,
            model=model,
            sampling_rate=16000,
            min_speech_duration_ms=int(config.min_segment_duration * 1000),
            min_silence_duration_ms=int(config.min_segment_duration * 1000 / 2),
        )

        if not speech_timestamps:
            return []

        # Build audio chunks and run per-segment MLX transcription
        backend = BackendRegistry().create("mlx")
        segments: list[Segment] = []

        for ts in speech_timestamps:
            start_s = ts["start"] / 16000.0
            end_s = ts["end"] / 16000.0
            duration = end_s - start_s

            # Split overly long segments further
            if duration > config.max_segment_duration:
                sub_segments = _split_long_segment(
                    audio_for_vad_path, start_s, end_s, backend, config
                )
                segments.extend(sub_segments)
            else:
                sub_seg = _transcribe_segment(
                    audio_for_vad_path, start_s, end_s, backend
                )
                if sub_seg is not None:
                    segments.append(sub_seg)

        return segments

    finally:
        if tmp_wav_path is not None:
            tmp_wav_path.unlink(missing_ok=True)


def _transcribe_segment(
    audio_path: str,
    start_s: float,
    end_s: float,
    backend,
) -> Segment | None:
    """Extract audio slice [start_s, end_s] and transcribe it with MLX."""
    try:
        import pydub
    except ImportError as exc:
        raise ASRProcessingError(
            "pydub is required for subtitle output. Install with `pip install pydub`."
        ) from exc

    try:
        audio = pydub.AudioSegment.from_wav(audio_path)
        # pydub uses milliseconds
        slice_ms = int(start_s * 1000)
        duration_ms = int((end_s - start_s) * 1000)
        chunk = audio[slice_ms : slice_ms + duration_ms]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        chunk.export(str(tmp_path), format="wav")

        try:
            from qwenasr_mlx_cli.core.types import TranscriptionRequest
            request = TranscriptionRequest(input_path=tmp_path, output_format="txt")
            result = backend.transcribe(request)
            text = result.text.strip()
            if not text:
                return None
            return Segment(start=start_s, end=end_s, text=text)
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:  # pragma: no cover
        # Skip segments that fail to transcribe
        return None


def _split_long_segment(
    audio_path: str,
    start_s: float,
    end_s: float,
    backend,
    config: SubtitleConfig,
) -> list[Segment]:
    """Split a long segment into sub-segments of max_segment_duration."""
    segments: list[Segment] = []
    cursor = start_s
    while cursor < end_s:
        sub_end = min(cursor + config.max_segment_duration, end_s)
        sub_seg = _transcribe_segment(audio_path, cursor, sub_end, backend)
        if sub_seg is not None:
            segments.append(sub_seg)
        cursor = sub_end
    return segments