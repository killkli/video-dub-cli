"""Unit tests for dub.project — project layout + initialization.

The two regressions these tests pin down both surfaced in real smoke runs:

1. ``initialize_project`` was unconditionally calling ``shutil.copy2`` even when
   the source video was already the canonical
   ``<project_dir>/01_raw_video/video.mp4`` (e.g. when the user passed an
   already-initialized project as the video argument). ``shutil.copy2``
   refuses to copy a file onto itself with ``SameFileError``. The fix is to
   compare resolved paths and skip the copy when src == dst.

2. The CLI flow passes the video through ``_prepare_project`` which delegates
   to ``initialize_project``. When the canonical video is reused, the call
   must complete without raising.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dub.errors import UserError
from dub.project import initialize_project


def test_initialize_project_copies_video_to_canonical_path(tmp_path: Path) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(b"\x00" * 2048)

    project_dir = tmp_path / "proj"
    initialize_project(project_dir, src)

    canonical = project_dir / "01_raw_video" / "video.mp4"
    assert canonical.exists()
    assert canonical.read_bytes() == src.read_bytes()


def test_initialize_project_does_not_copy_when_src_equals_dst(tmp_path: Path) -> None:
    """Re-initializing with a video that already lives at the canonical path
    must NOT raise shutil.SameFileError.

    Regression test for the real British Council smoke blocker:
      shutil.SameFileError: .../01_raw_video/video.mp4
    """
    project_dir = tmp_path / "proj"
    canonical = project_dir / "01_raw_video" / "video.mp4"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"\x00" * 2048)

    # Should NOT raise.
    initialize_project(project_dir, canonical)

    # File is intact (not truncated, not corrupted).
    assert canonical.exists()
    assert canonical.read_bytes() == b"\x00" * 2048


def test_initialize_project_creates_full_stage_layout(tmp_path: Path) -> None:
    src = tmp_path / "anywhere.mp4"
    src.write_bytes(b"x")

    project_dir = tmp_path / "proj"
    initialize_project(project_dir, src)

    # All canonical stage directories exist.
    for d in (
        "01_raw_video",
        "02_stems",
        "03_asr",
        "04_ref_audio",
        "05_translate",
        "05_translated_srt",
        "06_tts_wav",
        "07_final",
        ".dub",
    ):
        assert (project_dir / d).is_dir(), f"missing stage dir: {d}"


def test_initialize_project_raises_user_error_when_video_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    missing = tmp_path / "does-not-exist.mp4"

    with pytest.raises(UserError):
        initialize_project(project_dir, missing)


def test_initialize_project_handles_video_via_symlink_at_canonical_path(
    tmp_path: Path,
) -> None:
    """A symlink pointing at the canonical target must be treated as same-file
    and not raise SameFileError either. Resolving the path collapses the
    symlink to its real location.
    """
    project_dir = tmp_path / "proj"
    canonical = project_dir / "01_raw_video" / "video.mp4"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"\x00" * 1024)

    symlink = tmp_path / "link.mp4"
    symlink.symlink_to(canonical)

    # Should NOT raise.
    initialize_project(project_dir, symlink)

    assert canonical.exists()
    assert canonical.read_bytes() == b"\x00" * 1024
