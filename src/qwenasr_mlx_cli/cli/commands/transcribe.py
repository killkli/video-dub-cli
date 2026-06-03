from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from qwenasr_mlx_cli.core.exceptions import ASRProcessingError, BackendUnavailableError, InputValidationError
from qwenasr_mlx_cli.core.types import SubtitleConfig
from qwenasr_mlx_cli.pipelines.transcribe import run_transcription


def transcribe_command(
    input_path: Path,
    backend: str = "mlx",
    output_format: str = "txt",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    min_segment_duration: float = 0.3,
    max_segment_duration: float = 10.0,
    to_traditional: bool = False,
) -> Optional[str]:
    """Transcribe an audio file to text or subtitle formats.

    Use --output-format srt or --output-format vtt for timestamped subtitle output.
    Subtitle formats run a VAD segmentation stage and per-segment MLX transcription,
    so they are slower than plain text output.
    """
    console = Console()

    # Build subtitle config only when subtitle format is requested
    subtitle_config: SubtitleConfig | None = None
    if output_format in ("srt", "vtt"):
        subtitle_config = SubtitleConfig(
            min_segment_duration=min_segment_duration,
            max_segment_duration=max_segment_duration,
            output_format=output_format,
        )

    try:
        rendered = run_transcription(
            input_path=input_path,
            backend_name=backend,
            output_format=output_format,
            language=language,
            prompt=prompt,
            subtitle_config=subtitle_config,
            convert_simplified_to_traditional=to_traditional,
        )
    except (BackendUnavailableError, InputValidationError, ASRProcessingError, NotImplementedError) as exc:
        console.print(f"ERROR: {exc}")
        raise typer.Exit(code=2) from exc
    console.print(rendered)
    return rendered


if __name__ == "__main__":
    # Support: qwenasr-mlx transcribe <args>
    import sys
    typer.run(transcribe_command)