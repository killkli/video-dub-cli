"""progress.py — rich progress bar for pipeline stages."""

from __future__ import annotations

from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
)

# Stage display names
STAGE_LABELS = [
    "01 Stems (Demucs)",
    "02 ASR (qwenasr)",
    "03 Ref Audio",
    "04 Translate",
    "05 TTS",
    "06 Assemble",
]


def make_progress() -> Progress:
    """
    Build the top-level rich Progress bar for the 6 pipeline stages.
    Use transient=False so bars remain visible after completion.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        transient=False,
    )


def stage_label(name: str) -> str:
    """Map stage name (e.g. '01_stems') to a human-readable label."""
    labels = {
        "01_stems": "01 Stems (Demucs)",
        "02_asr": "02 ASR (qwenasr)",
        "03_ref_audio": "03 Ref Audio",
        "04_translate": "04 Translate",
        "05_tts": "05 TTS",
        "06_assemble": "06 Assemble",
    }
    return labels.get(name, name)