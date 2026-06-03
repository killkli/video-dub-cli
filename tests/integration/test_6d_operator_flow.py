from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
TOOL = ROOT / "tools" / "make_operator_qa_env.py"


@pytest.mark.integration
def test_6d_operator_flow(tmp_path: Path) -> None:
    env_build = subprocess.run(
        ["python3", str(TOOL)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    qa_root = Path(env_build.stdout.strip().splitlines()[-1])
    cfg = qa_root / "operator-config.yaml"
    video = qa_root / "test_short.mp4"
    project_dir = qa_root / "op_proj_test"
    if project_dir.exists():
        subprocess.run(["rm", "-rf", str(project_dir)], check=True)

    env = dict(**__import__("os").environ)
    env["DUB_ASR_TEST_FIXTURE_SRT"] = str(qa_root / "fake-asr.srt")
    env["DUB_PIPELINE_SCRIPTS_DIR"] = str(qa_root / "fake-skills")

    run_result = subprocess.run(
        [
            "dub", "run", str(video),
            "--source-lang", "en",
            "--target-lang", "zh",
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert run_result.returncode == 0, run_result.stderr or run_result.stdout

    status1 = subprocess.run(
        ["dub", "status", "--project-dir", str(project_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "06_assemble: done" in status1.stdout

    validate1 = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "validate ok:" in validate1.stdout

    clean_result = subprocess.run(
        ["dub", "clean", "--project-dir", str(project_dir), "--stage", "5"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "clean complete:" in clean_result.stdout
    assert not (project_dir / "06_tts_wav" / "line_1_tts.wav").exists()
    assert (project_dir / "07_final" / "video_dubbed_stem.mp4").exists()

    resume_result = subprocess.run(
        ["dub", "resume", "--project-dir", str(project_dir), "--config", str(cfg)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert resume_result.returncode == 0, resume_result.stderr or resume_result.stdout
    assert "resume complete:" in resume_result.stdout

    status2 = subprocess.run(
        ["dub", "status", "--project-dir", str(project_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "05_tts: done" in status2.stdout
    assert "06_assemble: skipped" in status2.stdout

    state = json.loads((project_dir / ".dub" / "state.json").read_text())
    assert state["stages"]["05_tts"]["status"] == "done"
    assert state["stages"]["06_assemble"]["status"] == "skipped"

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(project_dir / "07_final" / "video_dubbed_stem.mp4"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    assert 25 < duration < 35
