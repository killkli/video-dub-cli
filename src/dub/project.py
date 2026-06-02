"""Project directory utilities."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from dub.config import UserError


STANDARD_DIRS = [
    "01_raw_video",
    "02_stems",
    "03_asr",
    "04_ref_audio",
    "05_translated_srt",
    "06_tts_wav",
    "07_final",
    ".dub",
]


def create_project(dub_root: Path, video_path: Path) -> Path:
    """
    Create a new dub project directory under dub_root.

    Copies video.mp4 into 01_raw_video/.
    Returns the new project_dir path.
    """
    topic = video_path.stem
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_dir = dub_root / f"dub-{topic}-{timestamp}"

    for d in STANDARD_DIRS:
        (project_dir / d).mkdir(parents=True)

    shutil.copy(video_path, project_dir / "01_raw_video" / "video.mp4")
    return project_dir


def find_project(project_dir: Path) -> Path:
    """
    Validate project_dir contains .dub/ and return it.
    Raises UserError if not a valid project.
    """
    if not (project_dir / ".dub").exists():
        raise UserError(f"Not a dub project (no .dub/ dir): {project_dir}")
    return project_dir