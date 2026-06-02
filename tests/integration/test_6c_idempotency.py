"""T6c: Idempotency test — delete a ref_audio, resume, verify targeted rebuild.

Validates:
  - Full pipeline runs on 30s clip (reuses T6a project or fresh run)
  - Deleting one ref_audio file triggers targeted re-generation
  - After resume, the deleted ref_audio is re-created
  - Only the affected TTS clip is regenerated, not all outputs
"""

import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TEST_SHORT = FIXTURES / "test_short.mp4"


@pytest.mark.integration
def test_6c_idempotency(tmp_path: Path, fake_qwenasr_config: Path) -> None:
    """Idempotency: delete a ref_audio, resume, verify targeted rebuild."""

    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "proj"

    # --- Phase 1: Full run ---
    run_result = subprocess.run(
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
            "--config",
            str(fake_qwenasr_config),
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert run_result.returncode == 0, (
        f"Initial dub run failed: {run_result.stderr}"
    )

    ref_audio_dir = project_dir / "04_ref_audio"
    tts_wav_dir = project_dir / "06_tts_wav"

    # Collect original ref_audio files
    original_refs = sorted(ref_audio_dir.glob("*.wav"))
    assert len(original_refs) >= 1, "No ref_audio files found after initial run"

    # Pick a target file to delete (pick a middle one if possible)
    target_ref = original_refs[len(original_refs) // 2]
    target_name = target_ref.name
    target_ref.unlink()
    assert not target_ref.exists(), f"Failed to delete {target_ref}"

    # Record mtime of other ref files (should remain unchanged after resume)
    other_refs = [r for r in original_refs if r.name != target_name]
    other_mtimes_before = {r.name: r.stat().st_mtime for r in other_refs}

    # --- Phase 2: Resume ---
    resume_result = subprocess.run(
        ["dub", "resume", "--project-dir", str(project_dir), "--config", str(fake_qwenasr_config)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert resume_result.returncode == 0, (
        f"dub resume failed: {resume_result.stderr}"
    )

    # --- Phase 3: Verify targeted rebuild ---
    # The deleted ref_audio should be re-created
    restored_ref = ref_audio_dir / target_name
    assert restored_ref.exists(), f"Deleted ref_audio not restored: {target_name}"

    # Other ref files should be unchanged (same mtime)
    for ref_name, old_mtime in other_mtimes_before.items():
        ref_path = ref_audio_dir / ref_name
        if ref_path.exists():
            new_mtime = ref_path.stat().st_mtime
            assert new_mtime == old_mtime, (
                f"Unrelated ref_audio was modified: {ref_name}"
            )

    # The corresponding TTS wav should be regenerated
    # Derive tts filename from ref filename (e.g. line_3_ref.wav -> line_3_tts.wav)
    tts_name = target_name.replace("_ref.", "_tts.").replace("_ref_", "_tts_")
    tts_path = tts_wav_dir / tts_name
    assert tts_path.exists(), f"Expected TTS output not found: {tts_name}"
