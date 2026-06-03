from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from qwenasr_mlx_cli.cli.commands.transcribe import transcribe_command
from qwenasr_mlx_cli.core.exceptions import (
    ASRProcessingError,
    BackendUnavailableError,
    InputValidationError,
)
from qwenasr_mlx_cli.pipelines.batch import enumerate_batch_inputs


def batch_command(
    inputs: list[Path],
    output_dir: Path | None = None,
    output_format: str = "txt",
    min_segment_duration: float = 0.3,
    max_segment_duration: float = 10.0,
    convert_simplified_to_traditional: bool = False,
) -> None:
    """Transcribe multiple audio/video files with a progress bar."""
    console = Console()

    # Enumerate all input files (validates paths, errors descriptive)
    try:
        paths = enumerate_batch_inputs(inputs)
    except InputValidationError as exc:
        console.print(f"[red]ERROR: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not paths:
        console.print("[yellow]No supported audio/video files found.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Found {len(paths)} file(s) to process.[/dim]")

    results: dict[str, str] = {}  # path → "success" | "failed"
    errors: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing", total=len(paths))

        for path in paths:
            progress.update(task, description=f"  {path.name}")
            try:
                rendered = transcribe_command(
                    input_path=path,
                    backend="mlx",
                    output_format=output_format,
                    language=None,
                    prompt=None,
                    min_segment_duration=min_segment_duration,
                    max_segment_duration=max_segment_duration,
                    to_traditional=convert_simplified_to_traditional,
                )
                results[str(path)] = "success"

                # Write output file if output_dir is specified
                if output_dir is not None:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    out_name = path.stem + (
                        ".srt" if output_format == "srt"
                        else ".vtt" if output_format == "vtt"
                        else ".json" if output_format == "json"
                        else ".txt"
                    )
                    out_path = output_dir / out_name
                    out_path.write_text(rendered, encoding="utf-8")
                else:
                    console.print(rendered)

            except (BackendUnavailableError, InputValidationError, ASRProcessingError, NotImplementedError) as exc:
                results[str(path)] = "failed"
                errors.append(f"{path.name}: {exc}")
                console.print(f"\n[red]  ERROR processing {path.name}: {exc}[/red]")

            progress.advance(task)

    # Summary
    succeeded = sum(1 for v in results.values() if v == "success")
    failed = sum(1 for v in results.values() if v == "failed")
    console.print(f"\n[dim]Completed: {succeeded} succeeded, {failed} failed[/dim]")

    if errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for err in errors:
            console.print(f"  [red]- {err}[/red]")

    if failed > 0:
        raise typer.Exit(code=1)