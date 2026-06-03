"""Tests for the real-wire 03_ref_audio stage.

Covers the P3-T2 contract:
  - Stage invokes dubbing_extract_ref.py with three positional args
    (video.mp4, source.srt, output_dir/) where the output dir ends in "/".
  - is_done() requires 03_asr/video.srt to exist AND every cue 1..N to have
    a matching line_<i>_ref.wav in 04_ref_audio/.
  - Non-zero exit / missing SRT / missing raw mp4 → failed.
  - Partial production (script returned 0 but did not write all ref wavs)
    → failed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dub.config import DubConfig
from dub.runtime_paths import pipeline_script
from dub.stages.base import RefAudioStage


class DummyResult:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


SAMPLE_SRT_TWO_CUES = (
    "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"
)


def _make_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "01_raw_video").mkdir(parents=True)
    (proj / "01_raw_video" / "video.mp4").write_bytes(b"fake")
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(SAMPLE_SRT_TWO_CUES, encoding="utf-8")
    (proj / ".dub").mkdir(parents=True)
    return proj


# ── is_done contract ──────────────────────────────────────────────────────────


def test_is_done_false_when_srt_missing(tmp_path):
    proj = tmp_path / "proj"
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    assert RefAudioStage().is_done(proj) is False


def test_is_done_false_when_no_ref_dir(tmp_path):
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(SAMPLE_SRT_TWO_CUES, encoding="utf-8")
    assert RefAudioStage().is_done(proj) is False


def test_is_done_false_when_ref_count_below_srt(tmp_path):
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(SAMPLE_SRT_TWO_CUES, encoding="utf-8")
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    # line_2 missing → not done
    assert RefAudioStage().is_done(proj) is False


def test_is_done_true_when_all_refs_match_srt(tmp_path):
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(SAMPLE_SRT_TWO_CUES, encoding="utf-8")
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    (proj / "04_ref_audio" / "line_2_ref.wav").touch()
    assert RefAudioStage().is_done(proj) is True


def test_is_done_false_when_srt_is_empty(tmp_path):
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text("   \n", encoding="utf-8")
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    assert RefAudioStage().is_done(proj) is False


def test_is_done_false_when_srt_has_garbage_blocks(tmp_path):
    """SRT file with no recognizable timestamp arrows counts 0 cues."""
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(
        "this is not an srt\nat all\n", encoding="utf-8"
    )
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    assert RefAudioStage().is_done(proj) is False


def test_is_done_handles_crlf_srt(tmp_path):
    """Real-world SRTs use CRLF; we should still count cues correctly."""
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_bytes(
        b"1\r\n00:00:00,000 --> 00:00:01,000\r\nFirst line\r\n\r\n"
        b"2\r\n00:00:01,000 --> 00:00:02,000\r\nSecond line\r\n"
    )
    (proj / "04_ref_audio").mkdir(parents=True)
    (proj / "04_ref_audio" / "line_1_ref.wav").touch()
    (proj / "04_ref_audio" / "line_2_ref.wav").touch()
    assert RefAudioStage().is_done(proj) is True


# ── run() happy path ──────────────────────────────────────────────────────────


def test_ref_audio_stage_invokes_script_with_three_positional_args(tmp_path, monkeypatch):
    """The script contract is <video.mp4> <source.srt> <output_dir/>.

    The trailing slash matters — the script's Path.resolve() + mkdir depend on
    a directory, not a file path.
    """
    proj = _make_project(tmp_path)
    seen: dict = {}

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        seen["cmd"] = cmd
        # Simulate the script writing 2 ref wavs
        ref_dir = proj / "04_ref_audio"
        (ref_dir / "line_1_ref.wav").write_bytes(b"wav1")
        (ref_dir / "line_2_ref.wav").write_bytes(b"wav2")
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig()
    state = RefAudioStage().run(proj, cfg)

    assert state.status == "done"
    cmd = seen["cmd"]
    # python3 <script> <video.mp4> <srt> <out_dir/>  — exactly 5 elements.
    # The script's signature is three positional args (mp4, srt, outdir) after
    # the interpreter and the script path.
    assert len(cmd) == 5
    assert cmd[0] == "python3"
    assert cmd[1] == str(pipeline_script("dubbing_extract_ref.py"))
    assert cmd[2] == str(proj / "01_raw_video" / "video.mp4")
    assert cmd[3] == str(proj / "03_asr" / "video.srt")
    # The output dir MUST end with "/" — that's the script's signature.
    assert cmd[4].endswith("/"), f"output dir must end with '/': {cmd[4]}"
    assert cmd[4] == str(proj / "04_ref_audio") + "/"
    # artifacts reported
    assert sorted(state.artifacts) == ["line_1_ref.wav", "line_2_ref.wav"]
    assert state.output_dir == "04_ref_audio"
    # log file written
    assert (proj / ".dub" / "03_ref_audio.log").exists()


def test_ref_audio_stage_handles_crlf_srt_with_3_cues(tmp_path, monkeypatch):
    """Verify count parsing for a 3-cue CRLF SRT."""
    proj = _make_project(tmp_path)
    # rewrite SRT with 3 cues
    srt_text = (
        "1\r\n00:00:00,000 --> 00:00:01,000\r\nA\r\n\r\n"
        "2\r\n00:00:01,000 --> 00:00:02,000\r\nB\r\n\r\n"
        "3\r\n00:00:02,000 --> 00:00:03,000\r\nC\r\n"
    )
    (proj / "03_asr" / "video.srt").write_bytes(srt_text.encode("utf-8"))

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        ref_dir = proj / "04_ref_audio"
        for i in (1, 2, 3):
            (ref_dir / f"line_{i}_ref.wav").write_bytes(b"wav")
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = RefAudioStage().run(proj, DubConfig())
    assert state.status == "done"
    assert sorted(state.artifacts) == [
        "line_1_ref.wav",
        "line_2_ref.wav",
        "line_3_ref.wav",
    ]


# ── run() failure paths ───────────────────────────────────────────────────────


def test_ref_audio_stage_fails_when_raw_video_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "01_raw_video" / "video.mp4").unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when raw video missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = RefAudioStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "raw video missing" in state.error


def test_ref_audio_stage_fails_when_srt_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "03_asr" / "video.srt").unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when SRT missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = RefAudioStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "ASR SRT missing" in state.error


def test_ref_audio_stage_fails_on_nonzero_exit(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        if stdout is not None:
            stdout.write("ffmpeg failed\n")
        return DummyResult(2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = RefAudioStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "exited with code 2" in state.error
    assert ".dub/03_ref_audio.log" in state.error


def test_ref_audio_stage_fails_when_script_misses_some_refs(tmp_path, monkeypatch):
    """Even with exit 0, if the script didn't write every line_*_ref.wav the
    stage is failed (per the T0 contract — is_done checks all cue indices)."""
    proj = _make_project(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
        ref_dir = proj / "04_ref_audio"
        (ref_dir / "line_1_ref.wav").write_bytes(b"wav")
        # line_2 missing
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = RefAudioStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert state.error is not None
    assert "missing" in state.error
    assert "line_2_ref.wav" in state.error
