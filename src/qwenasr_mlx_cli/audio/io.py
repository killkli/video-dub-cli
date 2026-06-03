from pathlib import Path

from qwenasr_mlx_cli.core.exceptions import InputValidationError

SUPPORTED_SUFFIXES = {
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".mkv", ".avi"
}


def validate_media_input(path: Path) -> Path:
    if not path.exists():
        raise InputValidationError(f"Input does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise InputValidationError(f"Unsupported media type: {path.suffix}")
    return path
