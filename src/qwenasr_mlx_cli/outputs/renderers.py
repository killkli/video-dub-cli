import json
from dataclasses import asdict

from qwenasr_mlx_cli.core.types import TranscriptionResult
from qwenasr_mlx_cli.outputs.subtitle_renderer import render_srt, render_vtt
from qwenasr_mlx_cli.text.opencc_converter import convert_result_to_traditional


def render_output(
    result: TranscriptionResult,
    *,
    convert_simplified_to_traditional: bool = False,
) -> str:
    if convert_simplified_to_traditional:
        result = convert_result_to_traditional(result)

    if result.output_format == "txt":
        return result.text
    if result.output_format == "json":
        return json.dumps(
            {
                "text": result.text,
                "backend": result.backend_name,
                "segments": [asdict(segment) for segment in result.segments],
                "metadata": result.metadata,
            },
            ensure_ascii=False,
            indent=2,
        )
    if result.output_format in ("srt", "vtt"):
        if result.output_format == "srt":
            return render_srt(result.segments)
        return render_vtt(result.segments)
    raise ValueError(f"Unsupported output format: {result.output_format}")
