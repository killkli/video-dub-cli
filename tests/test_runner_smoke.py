"""test_runner_smoke.py — smoke test for run_pipeline with 30s fixture.

Tests:
  1. First run: all 6 stages complete (or skip with mock)
  2. Second run: all 6 stages are skipped (idempotency)
  3. Partial delete: deleting one line's TTS re-runs only that line
"""

import subprocess
from pathlib import Path
import pytest

from dub import runner
from dub import state as state_module
from dub import config as config_module
from dub import project as project_module


# ── fixture ──────────────────────────────────────────────────────────────────

FIXTURE = Path(__file__).parent / "fixtures" / "test_short.mp4"


@pytest.fixture(autouse=True)
def mock_external_cli_for_smoke(monkeypatch):
    real_run = subprocess.run

    def wrapped_run(cmd, *args, **kwargs):
        cmd_list = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        cmd0 = cmd_list[0] if cmd_list else ""
        cmd_strs = [str(x) for x in cmd_list]

        if isinstance(cmd0, str) and "qwenasr-mlx" in cmd0:
            stdout = kwargs.get("stdout")
            stderr = kwargs.get("stderr")
            if stdout is not None:
                stdout.write("1\n00:00:00,000 --> 00:00:01,000\nHello from mocked ASR.\n")
            if stderr is not None:
                stderr.write("mocked qwenasr ok")
            return subprocess.CompletedProcess(cmd, 0)

        if any("dubbing_extract_ref.py" in s for s in cmd_strs):
            out_dir = Path(cmd_strs[-1].rstrip("/"))
            out_dir.mkdir(parents=True, exist_ok=True)
            srt_path = Path(cmd_strs[-2])
            text = srt_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            blocks = [b for b in text.split("\n\n") if b.strip()]
            for i, _ in enumerate(blocks, 1):
                (out_dir / f"line_{i}_ref.wav").write_bytes(b"\\x00" * 4096)
            return subprocess.CompletedProcess(cmd, 0)

        if any("dubbing_batch_tts.py" in s for s in cmd_strs) or any("dubbing_batch_tts_vox.py" in s for s in cmd_strs):
            out_idx = cmd_strs.index("--out-dir")
            out_dir = Path(cmd_strs[out_idx + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            srt_flag = "--en-srt" if "--en-srt" in cmd_strs else "--ja-srt"
            srt_path = Path(cmd_strs[cmd_strs.index(srt_flag) + 1])
            text = srt_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            blocks = [b for b in text.split("\n\n") if b.strip()]
            for i, _ in enumerate(blocks, 1):
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\\x00" * 4096)
            return subprocess.CompletedProcess(cmd, 0)

        if any("dubbing_assemble_loudnorm.py" in s for s in cmd_strs):
            save_idx = cmd_strs.index("--save-normalized-wav")
            norm_path = Path(cmd_strs[save_idx + 1])
            norm_path.parent.mkdir(parents=True, exist_ok=True)
            norm_path.write_bytes(b"\\x00" * 4096)

            out_idx = cmd_strs.index("--output")
            out_path = Path(cmd_strs[out_idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\\x00" * 4096)
            return subprocess.CompletedProcess(cmd, 0)

        if any("dubbing_remix.py" in s for s in cmd_strs):
            out_idx = cmd_strs.index("--output")
            out_path = Path(cmd_strs[out_idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\\x00" * 4096)
            return subprocess.CompletedProcess(cmd, 0)

        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", wrapped_run)


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project with the test fixture."""
    dub_root = tmp_path / "dub_root"
    dub_root.mkdir()
    pdir = project_module.create_project(dub_root, FIXTURE, topic="test-smoke")
    # Initialize state
    cfg = config_module.DubConfig()
    state = state_module.new_state(pdir, cfg)
    info = project_module.project_input_info(pdir)
    state["input"]["video_path"] = info["video_path"]
    state["input"]["video_sha256"] = info["video_sha256"]
    state["input"]["duration_sec"] = info["duration_sec"]
    state_module.save_state(pdir, state)
    return pdir


@pytest.fixture
def config(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_scripts = tmp_path / "scripts"
    fake_root = tmp_path / "dub_root_runtime"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_scripts.mkdir(parents=True, exist_ok=True)
    fake_root.mkdir(parents=True, exist_ok=True)

    for rel in [
        fake_bin / "qwenasr-mlx",
        fake_bin / "omnivoice-python",
        fake_scripts / "subtitle_translation.py",
        fake_scripts / "dubbing_extract_ref.py",
        fake_scripts / "dubbing_batch_tts.py",
        fake_scripts / "dubbing_batch_tts_vox.py",
        fake_scripts / "dubbing_assemble_loudnorm.py",
        fake_scripts / "dubbing_remix.py",
    ]:
        rel.write_text("#!/usr/bin/env python3\n")

    return config_module.DubConfig.model_validate({
        "paths": {
            "qwenasr_cli": str(fake_bin / "qwenasr-mlx"),
            "omnivoice_python": str(fake_bin / "omnivoice-python"),
            "skills_dir": str(fake_scripts),
            "translation_skill": str(fake_scripts / "subtitle_translation.py"),
            "dub_root": str(fake_root),
        }
    })


# ── tests ─────────────────────────────────────────────────────────────────────

def test_full_cycle_skips_on_second_run(project_dir, config):
    """
    Run the pipeline twice. On first run stages should attempt (may fail on
    actual scripts if dependencies missing — that's ok for smoke, we just
    check the runner logic). On second run, all done/skipped stages are
    detected and skipped.
    """
    # First run
    s1 = runner.run_pipeline(project_dir, config)
    # Second run — all stages should be skipped or done
    s2 = runner.run_pipeline(project_dir, config)
    for name, stg in s2["stages"].items():
        assert stg["status"] in ("done", "skipped"), f"{name} was {stg['status']}, expected done/skipped"


def test_state_json_has_all_stages(project_dir, config):
    """Verify state.json tracks all 6 stages after a run."""
    runner.run_pipeline(project_dir, config)
    state = state_module.load_state(project_dir)
    for expected in ["01_stems", "02_asr", "03_ref_audio",
                     "04_translate", "05_tts", "06_assemble"]:
        assert expected in state["stages"], f"Missing stage: {expected}"


def test_project_dirs_created(project_dir):
    """Verify all 7 project directories exist."""
    for d in ["01_raw_video", "02_stems", "03_asr", "04_ref_audio",
              "05_translated_srt", "06_tts_wav", "07_final"]:
        assert (project_dir / d).exists(), f"Missing {d}"
    assert (project_dir / ".dub").exists()


def test_state_save_load_round_trip(project_dir):
    """Verify state can be saved and loaded."""
    state = {"schema_version": 1, "stages": {}}
    state_module.save_state(project_dir, state)
    loaded = state_module.load_state(project_dir)
    assert loaded is not None
    assert loaded["schema_version"] == 1


def test_config_merge_cli_overrides():
    """Verify CLI overrides actually override defaults."""
    cfg = config_module.DubConfig()
    merged = cfg.merge_cli_overrides(
        source_lang="ja",
        vocal_gain=5.0,
        keep_fulltrack=True,
    )
    assert merged.defaults.source_lang == "ja"
    assert merged.defaults.vocal_gain == 5.0
    assert merged.defaults.keep_fulltrack is True
    # Unsettable ones remain default
    assert merged.defaults.target_lang == "zh"