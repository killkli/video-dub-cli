"""T6a: 30s smoke test — end-to-end dub run with assertions.

Validates:
  - dub run completes with exit code 0
  - All 7 stage directories are created
  - 07_final/video_dubbed_stem.mp4 exists and is a valid MP4
  - ffprobe duration ≈ 30s (±5s tolerance)
  - SRT output contains Chinese characters
"""

import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TEST_SHORT = FIXTURES / "test_short.mp4"

# The 7 stage directories expected after a full run.
STAGE_DIRS = [
    "01_raw_video",
    "02_stems",
    "03_asr",
    "04_ref_audio",
    "05_translate",
    "06_tts_wav",
    "07_final",
]


@pytest.mark.integration
def test_6a_smoke(tmp_path: Path) -> None:
    """Smoke test: run the full pipeline on a 30s clip and verify outputs."""

    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "proj"

    # --- Run the full pipeline ---
    result = subprocess.run(
        [
            "dub",
            "run",
            str(TEST_SHORT),
            "--source-lang",
            "en",
            "--target-lang",
            "zh",
            "--project-dir",
            str(project_dir),
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        f"dub run failed (exit {result.returncode})\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # --- Verify all 7 stage directories exist ---
    for d in STAGE_DIRS:
        assert (project_dir / d).is_dir(), f"Missing stage directory: {d}"

    # --- Verify final MP4 ---
    final_mp4 = project_dir / "07_final" / "video_dubbed_stem.mp4"
    assert final_mp4.exists(), f"Final MP4 not found: {final_mp4}"

    # --- Duration check via ffprobe ---
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(final_mp4),
        ],
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, f"ffprobe failed: {probe.stderr}"
    duration = float(probe.stdout.strip())
    assert 25 < duration < 35, f"Duration {duration}s outside expected range [25, 35]"

    # --- Verify SRT contains Chinese characters ---
    srt_files = list(project_dir.glob("**/*.srt"))
    assert len(srt_files) >= 1, "No SRT files found in project directory"

    has_chinese = False
    for srt in srt_files:
        content = srt.read_text(encoding="utf-8", errors="replace")
        # Check for CJK Unified Ideographs range
        if any("\u4e00" <= ch <= "\u9fff" for ch in content):
            has_chinese = True
            break
    assert has_chinese, "No Chinese characters found in any SRT file"
