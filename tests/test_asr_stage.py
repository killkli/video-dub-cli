from __future__ import annotations

import sys
import wave
from types import SimpleNamespace

from dub.config import DubConfig
from dub.stages.base import ASRStage
from qwenasr_mlx_cli.backends.mlx_backend import _REQUIRED_SNAPSHOT_FILES, MLXBackend


def test_asr_stage_prefers_raw_video_and_writes_srt(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / "02_stems").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")
    (project_dir / "02_stems" / "video.mp4.vocals.wav").write_bytes(b"wav")

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
    assert "input=" in (project_dir / ".dub" / "02_asr.log").read_text(encoding="utf-8")


def test_asr_stage_falls_back_to_vocals_stem_when_raw_video_missing(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "02_stems").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "02_stems" / "video.mp4.vocals.wav").write_bytes(b"wav")

    seen = {}

    def fake_run_transcription(**kwargs):
        seen.update(kwargs)
        return "1\n00:00:00,000 --> 00:00:01,000\nHello world\n"

    monkeypatch.setattr("dub.stages.asr.run_transcription", fake_run_transcription)

    state = ASRStage().run(project_dir, DubConfig())

    assert state.status == "done"
    assert seen["input_path"] == project_dir / "02_stems" / "video.mp4.vocals.wav"


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


def test_mlx_backend_keeps_already_normalized_wav(tmp_path):
    wav_path = tmp_path / "mono16k.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)

    backend = MLXBackend()

    assert backend._load_audio(wav_path) == str(wav_path)


def test_mlx_backend_normalizes_non_16k_stereo_wav(tmp_path):
    wav_path = tmp_path / "stereo44k.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(44100)
        wav_file.writeframes(b"\x00\x00\x00\x00" * 160)

    backend = MLXBackend()
    normalized = backend._load_audio(wav_path)

    assert normalized != str(wav_path)
    with wave.open(normalized, "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 16000


def test_mlx_backend_prefers_complete_cached_snapshot(tmp_path, monkeypatch):
    cache_root = tmp_path / "hf"
    model_cache = cache_root / "hub" / "models--mlx-community--Qwen3-ASR-1.7B-bf16"
    snapshot = model_cache / "snapshots" / "abc123"
    (model_cache / "blobs").mkdir(parents=True)
    snapshot.mkdir(parents=True)
    for name in _REQUIRED_SNAPSHOT_FILES:
        (snapshot / name).write_text("x", encoding="utf-8")

    calls = []

    class FakeLoadedModel:
        def warm_up(self):
            calls.append("warm_up")

    class FakeQwen3ASR:
        @classmethod
        def from_pretrained(cls, source):
            calls.append(source)
            return FakeLoadedModel()

    monkeypatch.setenv("HF_HOME", str(cache_root))
    monkeypatch.setitem(sys.modules, "qwen3_asr_mlx", SimpleNamespace(Qwen3ASR=FakeQwen3ASR))
    MLXBackend._warmmed_up = False

    backend = MLXBackend()
    backend._ensure_model()

    assert calls[0] == str(snapshot)
    assert calls[1] == "warm_up"
