from dataclasses import replace
from pathlib import Path

from qwenasr_mlx_cli.audio.io import validate_media_input
from qwenasr_mlx_cli.backends.registry import BackendRegistry
from qwenasr_mlx_cli.core.types import (
    Segment,
    SubtitleConfig,
    TranscriptionRequest,
    TranscriptionResult,
)
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

    if subtitle_config is not None and output_format in ("srt", "vtt"):
        segments = segment_by_vad(
            audio_path=media_path,
            transcription_text="",
            config=subtitle_config,
            backend_name=backend_name,
            language=language,
            prompt=prompt,
        )
        if segments:
            result = TranscriptionResult(
                text=" ".join(segment.text.strip() for segment in segments if segment.text.strip()),
                output_format=output_format,
                backend_name=backend_name,
                segments=segments,
                metadata={"duration": segments[-1].end},
            )
            return render_output(
                result,
                convert_simplified_to_traditional=convert_simplified_to_traditional,
            )

        backend = BackendRegistry().create(backend_name)
        fallback_result = backend.transcribe(replace(request, output_format="txt"))
        fallback_segments: list[Segment] = []
        if fallback_result.text.strip():
            duration = float(fallback_result.metadata.get("duration") or 0.0)
            if duration <= 0:
                duration = 1.0
            fallback_segments = [
                Segment(start=0.0, end=duration, text=fallback_result.text.strip())
            ]
        result = replace(
            fallback_result,
            output_format=output_format,
            segments=fallback_segments,
        )
    else:
        backend = BackendRegistry().create(backend_name)
        result = backend.transcribe(request)

    return render_output(
        result,
        convert_simplified_to_traditional=convert_simplified_to_traditional,
    )
