from pathlib import Path

from qwenasr_mlx_cli.core.exceptions import InputValidationError


AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".mov", ".avi", ".mkv"})


def enumerate_batch_inputs(inputs: list[Path]) -> list[Path]:
    """Resolve input paths from files and directories.

    - File: validated and included if it has a supported audio extension.
    - Directory: recursively globbed for all matching audio extensions.
    - Missing paths raise InputValidationError with a descriptive message.
    """
    if not inputs:
        return []

    results: list[Path] = []
    for path in inputs:
        if not path.exists():
            raise InputValidationError(f"Input path does not exist: {path}")
        if path.is_file():
            if path.suffix.lower() in AUDIO_EXTENSIONS:
                results.append(path)
            # else: silently skip unsupported file types
        else:
            # Directory — recursively find all matching audio files
            found = [
                p for p in path.rglob("*")
                if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
            ]
            results.extend(sorted(found))

    return results