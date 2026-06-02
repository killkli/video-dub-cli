"""Tests for the real-wire 05_tts stage.

Covers the P3-T3 contract:
  - Stage invokes the OmniVoice or VoxCPM batch script with the exact
    CLI shape the T0 orchestration gate froze: <py> <script> --zh-srt
    <path> --en-srt|--ja-srt <path> --ref-dir <path> --out-dir <path>.
  - source_lang routing: en→dubbing_batch_tts.py, ja→dubbing_batch_tts_vox.py,
    any other→dubbing_batch_tts.py (OmniVoice default fallback).
  - is_done() requires 03_asr/video.srt + every cue 1..N to have BOTH
    a ref wav in 04_ref_audio/ AND a tts wav in 06_tts_wav/ of > 1000 bytes.
  - Pre-flight failures (missing zh SRT / ASR SRT / ref dir / script) →
    failed.
  - Post-flight: script exited 0 but didn't write every line_*_tts.wav →
    failed.
  - Non-zero exit → failed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dub.config import DubConfig, DefaultsConfig
from dub.stages.base import TtsStage


class DummyResult:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


SAMPLE_SRT_TWO_CUES = (
    "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"
)


def _make_project(tmp_path: Path) -> Path:
    """Build the minimum project layout that satisfies the TTS pre-flight."""
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(SAMPLE_SRT_TWO_CUES, encoding="utf-8")
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    (proj / "04_ref_audio" / "line_2_ref.wav").touch()
    (proj / "05_translated_srt").mkdir(parents=True)
    (proj / "05_translated_srt" / "video.zhtw.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n第一行\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n第二行\n",
        encoding="utf-8",
    )
    (proj / ".dub").mkdir(parents=True)
    return proj


def _populate_tts_wavs(proj: Path, n: int = 2) -> None:
    """Make n tts wavs of > 1000 bytes (the script's own skip threshold)."""
    out = proj / "06_tts_wav"
    out.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (out / f"line_{i}_tts.wav").write_bytes(b"\x00" * 2048)


# ── is_done contract ──────────────────────────────────────────────────────────


def test_is_done_false_when_asr_srt_missing(tmp_path):
    proj = tmp_path / "proj"
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    (proj / "06_tts_wav").mkdir(parents=True)
    _populate_tts_wavs(proj, 1)
    assert TtsStage().is_done(proj) is False


def test_is_done_false_when_ref_wav_missing(tmp_path):
    """SRT says 2 cues, but 04_ref_audio only has line_1."""
    proj = _make_project(tmp_path)
    (proj / "04_ref_audio" / "line_2_ref.wav").unlink()
    _populate_tts_wavs(proj, 2)
    assert TtsStage().is_done(proj) is False


def test_is_done_false_when_tts_wav_missing(tmp_path):
    proj = _make_project(tmp_path)
    _populate_tts_wavs(proj, 1)  # only line_1
    assert TtsStage().is_done(proj) is False


def test_is_done_false_when_tts_wav_too_small(tmp_path):
    """Zero-byte or sub-1KB tts wavs are not real — reject them.

    This matches the VoxCPM script's own skip-existing threshold of > 1000
    bytes, so a failed run that wrote 200-byte placeholders will be
    re-attempted rather than declared done.
    """
    proj = _make_project(tmp_path)
    out = proj / "06_tts_wav"
    out.mkdir(parents=True)
    (out / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
    (out / "line_2_tts.wav").write_bytes(b"")  # 0 bytes
    assert TtsStage().is_done(proj) is False


def test_is_done_true_when_all_match(tmp_path):
    proj = _make_project(tmp_path)
    _populate_tts_wavs(proj, 2)
    assert TtsStage().is_done(proj) is True


def test_is_done_handles_crlf_srt(tmp_path):
    """Real-world SRTs use CRLF — count parsing must not break."""
    proj = _make_project(tmp_path)
    (proj / "03_asr" / "video.srt").write_bytes(
        b"1\r\n00:00:00,000 --> 00:00:01,000\r\nFirst\r\n\r\n"
        b"2\r\n00:00:01,000 --> 00:00:02,000\r\nSecond\r\n"
    )
    _populate_tts_wavs(proj, 2)
    assert TtsStage().is_done(proj) is True


# ── run() routing & CLI shape ─────────────────────────────────────────────────


def test_run_routes_en_to_omnivoice_script(tmp_path, monkeypatch):
    """en → dubbing_batch_tts.py with --en-srt (NOT --ja-srt)."""
    proj = _make_project(tmp_path)
    seen: dict = {}

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        seen["cmd"] = cmd
        # Script doesn't actually run — we simulate the post-flight writes.
        _populate_tts_wavs(proj, 2)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = DubConfig()  # defaults.source_lang == "en"
    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    cmd = seen["cmd"]
    assert cmd[0] == str(cfg.paths.omnivoice_python)
    assert cmd[1] == str(cfg.paths.skills_dir / "dubbing_batch_tts.py")
    # --zh-srt <zh path> --en-srt <asr path> --ref-dir <ref> --out-dir <out>
    assert cmd[2:4] == ["--zh-srt", str(proj / "05_translated_srt" / "video.zhtw.srt")]
    assert cmd[4] == "--en-srt"
    assert cmd[5] == str(proj / "03_asr" / "video.srt")
    assert cmd[6:8] == ["--ref-dir", str(proj / "04_ref_audio")]
    assert cmd[8:10] == ["--out-dir", str(proj / "06_tts_wav")]
    assert len(cmd) == 10
    # No --ja-srt / --project-dir leaked in for the en route.
    assert "--ja-srt" not in cmd
    assert "--project-dir" not in cmd


def test_run_routes_ja_to_vox_cpm_script_with_ja_srt_flag(tmp_path, monkeypatch):
    """ja → dubbing_batch_tts_vox.py with --project-dir + --ja-srt.

    The real VoxCPM script requires --project-dir in addition to the
    explicit SRT / ref / out flags. A stage that omits it will fail before
    any TTS work starts.
    """
    proj = _make_project(tmp_path)
    seen: dict = {}

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        seen["cmd"] = cmd
        _populate_tts_wavs(proj, 2)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = DubConfig(defaults=DefaultsConfig(source_lang="ja"))
    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    cmd = seen["cmd"]
    assert cmd[1] == str(cfg.paths.skills_dir / "dubbing_batch_tts_vox.py")
    assert cmd[2:4] == ["--project-dir", str(proj)]
    assert cmd[4:6] == ["--zh-srt", str(proj / "05_translated_srt" / "video.zhtw.srt")]
    assert cmd[6] == "--ja-srt"
    assert cmd[7] == str(proj / "03_asr" / "video.srt")
    assert cmd[8:10] == ["--ref-dir", str(proj / "04_ref_audio")]
    assert cmd[10:12] == ["--out-dir", str(proj / "06_tts_wav")]
    # No --en-srt leaked in for the ja route.
    assert "--en-srt" not in cmd


def test_run_unknown_source_lang_falls_back_to_omnivoice(tmp_path, monkeypatch):
    """Unknown source_lang defaults to OmniVoice (en route) — fail-open
    rather than fail-closed so a typo in config doesn't silently kill the
    pipeline.
    """
    proj = _make_project(tmp_path)
    seen: dict = {}

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        seen["cmd"] = cmd
        _populate_tts_wavs(proj, 2)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    cfg = DubConfig(defaults=DefaultsConfig(source_lang="ko"))
    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    assert seen["cmd"][1] == str(cfg.paths.skills_dir / "dubbing_batch_tts.py")
    assert seen["cmd"][4] == "--en-srt"


# ── run() pre-flight failures ─────────────────────────────────────────────────


def test_run_fails_when_zh_srt_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "05_translated_srt" / "video.zhtw.srt").unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when zh SRT missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "zh SRT missing" in (state.error or "")


def test_run_fails_when_asr_srt_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "03_asr" / "video.srt").unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when ASR SRT missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "ASR SRT missing" in (state.error or "")


def test_run_fails_when_ref_dir_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    # Clear the contents so we can remove the dir itself.
    import shutil

    shutil.rmtree(proj / "04_ref_audio")

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when ref dir missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "ref dir missing" in (state.error or "")


# ── run() script-level failures ───────────────────────────────────────────────


def test_run_fails_on_nonzero_exit(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        if stdout is not None:
            stdout.write("OmniVoice OOM\n")
        return DummyResult(137)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "exited with code 137" in (state.error or "")
    assert ".dub/05_tts.log" in (state.error or "")


def test_run_fails_when_script_misses_some_tts_wavs(tmp_path, monkeypatch):
    """Even with exit 0, partial production = failed.

    Mirrors ref_audio's invariant: a per-segment pipeline can succeed for
    some cues and silently fail for others. is_done's whole point is to
    refuse that half-state.
    """
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        out = proj / "06_tts_wav"
        out.mkdir(parents=True, exist_ok=True)
        # line_1 succeeds, line_2 missing
        (out / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "1/2" in (state.error or "")
    assert "line_2_tts.wav" in (state.error or "")


def test_run_fails_when_script_writes_only_placeholder_bytes(tmp_path, monkeypatch):
    """A script that exits 0 but only writes zero-byte files must not be
    accepted as 'done' — the byte-size gate is the same one we use in
    is_done, so post-flight and is_done stay consistent.
    """
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        out = proj / "06_tts_wav"
        out.mkdir(parents=True, exist_ok=True)
        (out / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
        (out / "line_2_tts.wav").write_bytes(b"")  # placeholder
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "missing or too small" in (state.error or "")


# ── run() success artifacts ───────────────────────────────────────────────────


def test_run_reports_artifacts_and_output_dir(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        _populate_tts_wavs(proj, 2)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = TtsStage().run(proj, DubConfig())

    assert state.status == "done"
    assert sorted(state.artifacts) == ["line_1_tts.wav", "line_2_tts.wav"]
    assert state.output_dir == "06_tts_wav"
    # Log file written
    assert (proj / ".dub" / "05_tts.log").exists()
