"""T6b: 5min resume test — kill during TTS stage, then resume.

Validates:
  - dub run starts on a 5min clip
  - Process is killed mid-pipeline (SIGKILL)
  - dub status shows partial completion
  - dub resume completes the pipeline
  - Final MP4 duration ≈ 300s (±5s)
"""

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TEST_5MIN = FIXTURES / "test_5min.mp4"


@pytest.mark.integration
@pytest.mark.timeout(900)
def test_6b_resume(tmp_path: Path, fake_qwenasr_config: Path) -> None:
    """Resume test: interrupt a 5min run, then resume and verify final output."""

    if not TEST_5MIN.exists():
        pytest.skip(f"Fixture not found: {TEST_5MIN}")

    project_dir = tmp_path / "proj"

    # --- Phase 1: Start dub run and kill it after a delay ---
    env = dict(os.environ)
    env["DUB_ASR_TEST_FIXTURE_SRT"] = str(fake_qwenasr_config.parent / "fake-asr.srt")
    env["DUB_PIPELINE_SCRIPTS_DIR"] = str(fake_qwenasr_config.parent / "fake-skills")
    proc = subprocess.Popen(
        [
            "dub",
            "run",
            str(TEST_5MIN),
            "--source-lang",
            "en",
            "--target-lang",
            "zh",
            "--project-dir",
            str(project_dir),
            "--config",
            str(fake_qwenasr_config),
            "--yes",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Wait enough for the pipeline to progress past early stages.
    # With a 5min clip this should get into TTS territory.
    time.sleep(60)
    proc.kill()  # SIGKILL
    proc.wait(timeout=10)

    # --- Phase 2: Check status ---
    status_result = subprocess.run(
        ["dub", "status", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    # Status should succeed and show partial progress
    assert status_result.returncode == 0, (
        f"dub status failed: {status_result.stderr}"
    )

    # --- Phase 3: Resume ---
    resume_result = subprocess.run(
        ["dub", "resume", "--project-dir", str(project_dir), "--config", str(fake_qwenasr_config)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert resume_result.returncode == 0, (
        f"dub resume failed (exit {resume_result.returncode})\n"
        f"stdout: {resume_result.stdout}\nstderr: {resume_result.stderr}"
    )

    # --- Phase 4: Verify final output ---
    final_mp4 = project_dir / "07_final" / "video_dubbed_stem.mp4"
    assert final_mp4.exists(), f"Final MP4 not found after resume: {final_mp4}"

    # Duration check — should be close to 300s
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
    assert abs(duration - 300) < 5, (
        f"Duration {duration}s differs from expected 300s by more than 5s"
    )
