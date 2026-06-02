"""project.py — project directory creation + layout helpers."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from dub.errors import UserError


# Stage output directories (1-indexed to match design)
STAGE_DIRS = [
    "01_raw_video",
    "02_stems",
    "03_asr",
    "04_ref_audio",
    "05_translated_srt",
    "06_tts_wav",
    "07_final",
]

STAGE_NAMES = ["01_stems", "02_asr", "03_ref_audio", "04_translate", "05_tts", "06_assemble"]


def video_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_duration_sec(path: Path) -> float:
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def create_project(dub_root: Path, video_path: Path, topic: str | None = None) -> Path:
    """
    Create a new dubbing project directory and populate 01_raw_video.
    Returns the project dir path.
    """
    if not video_path.exists():
        raise UserError(f"Video file not found: {video_path}")

    # Derive topic from video filename
    if topic is None:
        stem = video_path.stem
        topic = stem.strip().replace(" ", "-").replace("_", "-")

    # Unique project dir: dub-{topic}-{timestamp}
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    project_dir = dub_root / f"dub-{topic}-{ts}"

    if project_dir.exists():
        raise UserError(f"Project directory already exists: {project_dir}")

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".dub").mkdir(exist_ok=True)

    # Create all stage directories
    for d in STAGE_DIRS:
        (project_dir / d).mkdir(exist_ok=True)

    # Copy video to 01_raw_video/
    dst = project_dir / "01_raw_video" / "video.mp4"
    shutil.copy2(video_path, dst)

    return project_dir


def project_input_info(project_dir: Path) -> dict:
    """Return {video_path, sha256, duration_sec} for the project."""
    video_path = project_dir / "01_raw_video" / "video.mp4"
    sha = video_sha256(video_path)
    dur = get_duration_sec(video_path)
    return {"video_path": str(video_path), "video_sha256": sha, "duration_sec": dur}