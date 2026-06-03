import shutil
import sys

import typer
from rich.console import Console

from qwenasr_mlx_cli.backends.registry import BackendRegistry


def doctor_command() -> None:
    console = Console()
    registry = BackendRegistry()
    console.print(f"python: {sys.version.split()[0]}")
    console.print(f"ffmpeg: {'found' if shutil.which('ffmpeg') else 'missing'}")
    for name in registry.names():
        backend = registry.create(name)
        console.print(f"backend:{name}: {'available' if backend.available() else 'missing optional dependency'}")
    raise typer.Exit(code=0)
