from __future__ import annotations

from dub.config import DubConfig
from dub.stages.base import ASRStage


def test_asr_stage_invokes_repo_pipeline_and_writes_srt(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    seen = {}

    def fake_run_transcription(**kwargs):
        seen.update(kwargs)
        return "1\n00:00:00,000 --> 00:00:01,000\nHello world\n"

    monkeypatch.setattr("dub.stages.asr.run_transcription", fake_run_transcription)
    cfg = DubConfig()
    state = ASRStage().run(project_dir, cfg)

    assert state.status == "done"
    assert seen["input_path"] == project_dir / "01_raw_video" / "video.mp4"
    assert seen["backend_name"] == "mlx"
    assert seen["output_format"] == "srt"
    assert (project_dir / "03_asr" / "video.srt").read_text(encoding="utf-8").strip().startswith("1")


def test_asr_stage_fails_when_repo_pipeline_raises(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fake_run_transcription(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("dub.stages.asr.run_transcription", fake_run_transcription)
    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "repo ASR pipeline failed" in state.error


def test_asr_stage_fails_on_empty_output(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fake_run_transcription(**kwargs):
        return "\n"

    monkeypatch.setattr("dub.stages.asr.run_transcription", fake_run_transcription)
    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "empty SRT" in state.error


def test_asr_stage_test_mode_copies_fixture_srt(tmp_path, monkeypatch):
    """When DUB_ASR_TEST_FIXTURE_SRT points to a real SRT, the stage copies it
    to 03_asr/video.srt and never invokes run_transcription."""
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    fixture = tmp_path / "fixture.srt"
    fixture.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n哈囉 fixture\n",
        encoding="utf-8",
    )

    def fail_if_called(**kwargs):
        raise AssertionError("run_transcription should not run in test fixture mode")

    monkeypatch.setattr("dub.stages.asr.run_transcription", fail_if_called)
    monkeypatch.setenv("DUB_ASR_TEST_FIXTURE_SRT", str(fixture))

    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "done"
    assert state.artifacts == ["video.srt"]
    assert state.output_dir == "03_asr"
    assert (project_dir / "03_asr" / "video.srt").read_text(encoding="utf-8") == fixture.read_text(
        encoding="utf-8"
    )


def test_asr_stage_test_mode_missing_fixture_fails(tmp_path, monkeypatch):
    """If DUB_ASR_TEST_FIXTURE_SRT points to a missing file, the stage fails
    with a clear error rather than silently running the real pipeline."""
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fail_if_called(**kwargs):
        raise AssertionError("run_transcription should not run in test fixture mode")

    monkeypatch.setattr("dub.stages.asr.run_transcription", fail_if_called)
    monkeypatch.setenv("DUB_ASR_TEST_FIXTURE_SRT", "/path/that/does/not/exist.srt")

    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "test fixture SRT not found" in state.error


def test_asr_stage_test_mode_backend_fail_short_circuits(tmp_path, monkeypatch):
    """When DUB_ASR_TEST_BACKEND_FAIL is set, the stage records a failed
    state without invoking run_transcription (hermetic failure path)."""
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")

    def fail_if_called(**kwargs):
        raise AssertionError("run_transcription should not run in test fail mode")

    monkeypatch.setattr("dub.stages.asr.run_transcription", fail_if_called)
    monkeypatch.setenv("DUB_ASR_TEST_BACKEND_FAIL", "1")

    state = ASRStage().run(project_dir, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "test-mode forced backend failure" in state.error
