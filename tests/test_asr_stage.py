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
