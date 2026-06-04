from dataclasses import replace
from pathlib import Path

from qwenasr_mlx_cli.audio.io import validate_media_input
from qwenasr_mlx_cli.backends.registry import BackendRegistry
from qwenasr_mlx_cli.core.types import Segment, SubtitleConfig, TranscriptionRequest
from qwenasr_mlx_cli.outputs.renderers import render_output
from qwenasr_mlx_cli.segmentation.vad import segment_by_vad


def run_transcription(
    input_path: Path,
    backend_name: str,
    output_format: str,
    language: str | None = None,
    prompt: str | None = None,
    subtitle_config: SubtitleConfig | None = None,
    convert_simplified_to_traditional: bool = False,
) -> str:
    media_path = validate_media_input(input_path)
    request = TranscriptionRequest(
        input_path=media_path,
        output_format=output_format,
        language=language,
        prompt=prompt,
        subtitle_config=subtitle_config,
    )
    backend = BackendRegistry().create(backend_name)
    result = backend.transcribe(request)

    # Run VAD segmentation when subtitle output is requested
    if subtitle_config is not None and output_format in ("srt", "vtt"):
        segments = segment_by_vad(
            audio_path=media_path,
            transcription_text=result.text,
            config=subtitle_config,
        )
        if not segments and result.text.strip():
            duration = float(result.metadata.get("duration") or 0.0)
            if duration <= 0:
                duration = 1.0
            segments = [
                Segment(start=0.0, end=duration, text=result.text.strip())
            ]
        result = replace(result, segments=segments)

    return render_output(
        result,
        convert_simplified_to_traditional=convert_simplified_to_traditional,
    )
