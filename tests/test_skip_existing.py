"""Tests for skip-existing (is_done) on all 6 stages."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dub.stages.base import (
    StemsStage,
    ASRStage,
    RefAudioStage,
    TranslateStage,
    TTSStage,
    AssembleStage,
    get_stage,
)


STAGES = [
    ("01_stems", StemsStage()),
    ("02_asr", ASRStage()),
    ("03_ref_audio", RefAudioStage()),
    ("04_translate", TranslateStage()),
    ("05_tts", TTSStage()),
    ("06_assemble", AssembleStage()),
]


def make_proj(tmp: Path, name: str) -> Path:
    p = tmp / name
    p.mkdir(parents=True)
    return p


# ─── All artifacts exist → is_done = True ──────────────────────────────────────

@pytest.mark.parametrize("stage_name,stage", STAGES)
def test_is_done_true_when_all_artifacts_exist(tmp_path, stage_name, stage):
    proj = make_proj(tmp_path, "proj1")

    if stage_name == "01_stems":
        (proj / "02_stems").mkdir()
        (proj / "02_stems" / "vocals.wav").touch()
        (proj / "02_stems" / "instrumental.wav").touch()
    elif stage_name == "02_asr":
        (proj / "03_asr").mkdir()
        (proj / "03_asr" / "video.srt").touch()
    elif stage_name == "03_ref_audio":
        # Real-wire ref_audio: 03_asr/video.srt cues must match 04_ref_audio
        # line_*_ref.wav count (per P3-T2 contract).
        (proj / "03_asr").mkdir()
        (proj / "03_asr" / "video.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n",
            encoding="utf-8",
        )
        (proj / "04_ref_audio").mkdir()
        (proj / "04_ref_audio" / "line_1_ref.wav").touch()
        (proj / "04_ref_audio" / "line_2_ref.wav").touch()
    elif stage_name == "04_translate":
        (proj / "05_translated_srt").mkdir()
        (proj / "05_translated_srt" / "video.zhtw.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n你好世界\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n第二行翻譯\n",
            encoding="utf-8",
        )
    elif stage_name == "05_tts":
        # Real-wire tts: ASR SRT cues + matching 04_ref_audio/line_*_ref.wav
        # + matching 06_tts_wav/line_*_tts.wav of non-trivial size
        # (per P3-T3 contract — mirrors 03_ref_audio's invariant).
        (proj / "03_asr").mkdir()
        (proj / "03_asr" / "video.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n",
            encoding="utf-8",
        )
        (proj / "04_ref_audio").mkdir()
        (proj / "04_ref_audio" / "line_1_ref.wav").touch()
        (proj / "04_ref_audio" / "line_2_ref.wav").touch()
        (proj / "06_tts_wav").mkdir()
        # > 1000 bytes — the VoxCPM script's own skip threshold, mirrored here
        # so is_done treats zero-byte placeholders the same way the script does.
        (proj / "06_tts_wav" / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
        (proj / "06_tts_wav" / "line_2_tts.wav").write_bytes(b"\x00" * 2048)
    elif stage_name == "06_assemble":
        # Real-wire assemble: 07_final/video_dubbed_stem.mp4 must exist with
        # non-trivial size (the byte-size gate mirrors T2/T3 wav gates).
        (proj / "07_final").mkdir()
        (proj / "07_final" / "video_dubbed_stem.mp4").write_bytes(b"\x00" * 2048)

    assert stage.is_done(proj) is True


# ─── No artifacts → is_done = False ───────────────────────────────────────────

@pytest.mark.parametrize("stage_name,stage", STAGES)
def test_is_done_false_when_no_artifacts(tmp_path, stage_name, stage):
    proj = make_proj(tmp_path, "proj2")
    # Ensure target dir does not exist at all
    if stage_name == "01_stems":
        assert not (proj / "02_stems").exists()
    assert stage.is_done(proj) is False


# ─── Some artifacts missing → is_done = False ────────────────────────────────

@pytest.mark.parametrize("stage_name,stage", STAGES)
def test_is_done_false_when_some_artifacts_missing(tmp_path, stage_name, stage):
    proj = make_proj(tmp_path, "proj3")

    if stage_name == "01_stems":
        (proj / "02_stems").mkdir()
        (proj / "02_stems" / "vocals.wav").touch()
        # instrumental.wav missing
    elif stage_name == "02_asr":
        (proj / "03_asr").mkdir()
        # no .srt files
    elif stage_name == "03_ref_audio":
        (proj / "04_ref_audio").mkdir()
        (proj / "04_ref_audio" / "line_1_ref.wav").touch()
        # line_2 missing
    elif stage_name == "04_translate":
        # dir missing entirely
        pass
    elif stage_name == "05_tts":
        (proj / "06_tts_wav").mkdir()
        # no wav files
    elif stage_name == "06_assemble":
        (proj / "07_final").mkdir()
        # no mp4 files

    assert stage.is_done(proj) is False


# ─── Stage directory exists but empty → is_done = False ───────────────────────

@pytest.mark.parametrize("stage_name,stage", STAGES)
def test_is_done_false_when_dir_empty(tmp_path, stage_name, stage):
    proj = make_proj(tmp_path, "proj4")

    if stage_name == "01_stems":
        (proj / "02_stems").mkdir()
    elif stage_name == "02_asr":
        (proj / "03_asr").mkdir()
    elif stage_name == "03_ref_audio":
        (proj / "04_ref_audio").mkdir()
    elif stage_name == "04_translate":
        (proj / "05_translated_srt").mkdir()
    elif stage_name == "05_tts":
        (proj / "06_tts_wav").mkdir()
    elif stage_name == "06_assemble":
        (proj / "07_final").mkdir()

    assert stage.is_done(proj) is False


# ─── Artifact removed mid-session → is_done = False ────────────────────────────

def test_is_done_false_after_manual_deletion(tmp_path):
    proj = make_proj(tmp_path, "proj5")
    (proj / "03_asr").mkdir()
    srt = proj / "03_asr" / "video.srt"
    srt.touch()

    asr = ASRStage()
    assert asr.is_done(proj) is True

    srt.unlink()
    assert asr.is_done(proj) is False


# ─── get_stage registry ───────────────────────────────────────────────────────

def test_get_stage_registry():
    assert get_stage("01_stems").name == "01_stems"
    assert get_stage("06_assemble").name == "06_assemble"
    with pytest.raises(KeyError):
        get_stage("99_invalid")