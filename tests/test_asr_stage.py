from __future__ import annotations

import subprocess
from pathlib import Path

from dub.config import DubConfig
from dub.stages.base import ASRStage


class DummyResult:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


def test_asr_stage_invokes_qwenasr_and_writes_srt(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    seen = {}

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        seen["cmd"] = cmd
        assert stdout is not None
        stdout.write("1\n00:00:00,000 --> 00:00:01,000\nHello world\n")
        if stderr is not None:
            stderr.write("ok")
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = DubConfig()
    state = ASRStage().run(project_dir, cfg)

    assert state.status == "done"
    assert seen["cmd"][0] == str(cfg.paths.qwenasr_cli)
    assert seen["cmd"][1:4] == ["transcribe", str(project_dir / "01_raw_video" / "video.mp4"), "--output-format"]
    assert (project_dir / "03_asr" / "video.srt").read_text(encoding="utf-8").strip().startswith("1")


def test_asr_stage_fails_on_nonzero_exit(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        return DummyResult(3)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "exited with code 3" in state.error


def test_asr_stage_fails_on_empty_output(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        assert stdout is not None
        stdout.write("\n")
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "empty SRT" in state.error
