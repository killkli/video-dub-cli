"""Tests for the real-wire 06_assemble stage.

Covers the P3-T4 contract (frozen by the T0 orchestration gate 2026-06-02):

Pipeline stages exercised (with subprocess.run mocked):
  1. dubbing_assemble_loudnorm.py — REQUIRED when tts_normalized missing;
                                    builds a time-aligned fulltrack and saves
                                    06_tts_wav/tts_normalized.wav
  2. dubbing_remix.py            — REQUIRED, runs on every fresh run
  3. legacy alias copy           — REQUIRED, only copies if alias missing
  4. keep_fulltrack=True         — retains the fulltrack mp4 from step 1

Artifact contract (the test fixtures must keep in sync with this):
  - 01_raw_video/video.mp4            (input)
  - 06_tts_wav/line_*_tts.wav         (input; per-cue TTS wavs)
  - 07_final/video_dubbed_stem.mp4    (primary output, REQUIRED)
  - 07_final/video_dubbed.mp4         (legacy alias, copy of stem)
  - 07_final/video_dubbed_fulltrack.mp4 (fulltrack output, only if keep_fulltrack)

Failure semantics:
  - remix non-zero exit  → stage failed, no half-written stem
  - remix exit 0 but stem missing/too small → stage failed
  - time-aligned loudnorm builder non-zero  → stage failed
  - Pre-flight: missing source video / no tts wavs / missing remix script → failed
  - keep_fulltrack=True: missing loudnorm script or zh SRT → failed
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dub.config import DubConfig, DefaultsConfig
from dub.stages.base import AssembleStage


class DummyResult:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


# Two cues is the smallest case that exercises per-line iteration.
SAMPLE_SRT_TWO_CUES = (
    "1\n00:00:00,000 --> 00:00:01,000\nFirst line\n\n"
    "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"
)


def _make_project(tmp_path: Path) -> Path:
    """Build the minimum project layout that satisfies the assemble pre-flight.

    The stage's pre-flight checks 01_raw_video/video.mp4, translated zh SRT,
    and the
    presence of at least one 06_tts_wav/line_*_tts.wav. We provide real
    bytes (>= 1KB) so the is_done byte-size gate is also satisfied.
    """
    proj = tmp_path / "proj"
    (proj / "01_raw_video").mkdir(parents=True)
    (proj / "01_raw_video" / "video.mp4").write_bytes(b"\x00" * 2048)
    (proj / "05_translated_srt").mkdir(parents=True)
    (proj / "05_translated_srt" / "video.zhtw.srt").write_text(
        SAMPLE_SRT_TWO_CUES.replace("First", "第一").replace("Second", "第二"),
        encoding="utf-8",
    )
    (proj / "06_tts_wav").mkdir(parents=True)
    for i in (1, 2):
        (proj / "06_tts_wav" / f"line_{i}_tts.wav").write_bytes(b"\x00" * 2048)
    (proj / ".dub").mkdir(parents=True)
    return proj


def _record_subprocess(
    proj: Path,
    *,
    remix_should_write: bool = True,
    loudnorm_should_write: bool = True,
    remix_returncode: int = 0,
    loudnorm_returncode: int = 0,
    step1_returncode: int = 0,
    step1_should_write_normalized: bool = True,
): 
    """Return a fake subprocess.run that records calls and simulates outputs.

    - When the call is the time-aligned loudnorm builder, optionally write
      06_tts_wav/tts_normalized.wav and the requested fulltrack mp4.
    - When the call is remix, write 07_final/video_dubbed_stem.mp4 (if
      remix_should_write) — otherwise simulate silent failure (no file).
    """
    calls: list[dict] = []
    tts_dir = proj / "06_tts_wav"
    final_dir = proj / "07_final"
    final_dir.mkdir(parents=True, exist_ok=True)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        calls.append({"cmd": list(cmd)})
        cmd_strs = [str(x) for x in cmd]

        # Time-aligned loudnorm builder: required source of tts_normalized.wav.
        if any("dubbing_assemble_loudnorm" in s for s in cmd_strs):
            if step1_returncode == 0:
                if step1_should_write_normalized:
                    save_idx = cmd_strs.index("--save-normalized-wav")
                    norm_path = Path(cmd_strs[save_idx + 1])
                    norm_path.parent.mkdir(parents=True, exist_ok=True)
                    norm_path.write_bytes(b"\x00" * 4096)

            if step1_returncode == 0 and loudnorm_should_write:
                # Find --output value
                out_idx = cmd_strs.index("--output")
                out_path = Path(cmd_strs[out_idx + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"\x00" * 4096)
            return DummyResult(step1_returncode)

        # Remix pass: --output is stem mp4
        if any("dubbing_remix" in s for s in cmd_strs):
            if remix_returncode == 0 and remix_should_write:
                out_idx = cmd_strs.index("--output")
                out_path = Path(cmd_strs[out_idx + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"\x00" * 4096)
            return DummyResult(remix_returncode)

        # Default: success with no side effects.
        return DummyResult(0)

    return fake_run, calls


# ── is_done contract ──────────────────────────────────────────────────────────


def test_is_done_false_when_stem_missing(tmp_path):
    proj = tmp_path / "proj"
    (proj / "07_final").mkdir(parents=True)
    # Only the legacy alias is present; stem is the canonical artifact.
    (proj / "07_final" / "video_dubbed.mp4").write_bytes(b"\x00" * 2048)
    assert AssembleStage().is_done(proj) is False


def test_is_done_false_when_stem_is_too_small(tmp_path):
    """Stub 200-byte mp4 must not be accepted as 'done'.

    Mirrors the >=1000 byte gate T2/T3 use for ref/tts wavs. A failed remix
    that wrote a placeholder is not a successful run.
    """
    proj = tmp_path / "proj"
    (proj / "07_final").mkdir(parents=True)
    (proj / "07_final" / "video_dubbed_stem.mp4").write_bytes(b"x")
    assert AssembleStage().is_done(proj) is False


def test_is_done_false_when_final_dir_missing(tmp_path):
    proj = tmp_path / "proj"
    assert AssembleStage().is_done(proj) is False


def test_is_done_true_when_stem_has_real_size(tmp_path):
    proj = tmp_path / "proj"
    (proj / "07_final").mkdir(parents=True)
    (proj / "07_final" / "video_dubbed_stem.mp4").write_bytes(b"\x00" * 2048)
    assert AssembleStage().is_done(proj) is True


# ── run() command assembly — remix is the spine ──────────────────────────────


def test_run_invokes_remix_with_exact_cli_shape(tmp_path, monkeypatch):
    """The remix CLI is frozen by T0 contract: <py> <remix> --project-dir <p>
    --vocal-mix <normalized.wav> --output <stem.mp4>
    --vocal-gain <db> --inst-gain <db>.

    A regression here will break the real dubbing_remix.py at runtime.
    """
    proj = _make_project(tmp_path)
    # Pre-populate tts_normalized.wav so we skip the ffmpeg concat/loudnorm
    # (they're a pre-req, not the spine we're testing here).
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig()
    state = AssembleStage().run(proj, cfg)

    assert state.status == "done"
    remix_calls = [c for c in calls if "dubbing_remix" in c["cmd"][1]]
    assert len(remix_calls) == 1, "remix must be invoked exactly once"
    cmd = remix_calls[0]["cmd"]
    # [python3, <remix.py>, --project-dir, <p>, --vocal-mix, <tts_normalized>,
    #  --output, <stem.mp4>, --vocal-gain, <db>, --inst-gain, <db>]
    assert cmd[0] == "python3"
    assert cmd[1] == str(cfg.paths.skills_dir / "dubbing_remix.py")
    assert cmd[2:4] == ["--project-dir", str(proj)]
    assert cmd[4:6] == ["--vocal-mix", str(proj / "06_tts_wav" / "tts_normalized.wav")]
    assert cmd[6:8] == ["--output", str(proj / "07_final" / "video_dubbed_stem.mp4")]
    assert cmd[8:10] == ["--vocal-gain", str(cfg.defaults.vocal_gain)]
    assert cmd[10:12] == ["--inst-gain", str(cfg.defaults.inst_gain)]
    assert len(cmd) == 12


def test_run_provides_compat_instrumental_path_expected_by_real_remix(tmp_path, monkeypatch):
    """Real dubbing_remix.py currently resolves 02_stems/video.mp4.instrumental.wav.
    The stage must provide a compatibility alias from canonical instrumental.wav
    so the real script can succeed on current committed skills.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    (proj / "02_stems").mkdir(parents=True, exist_ok=True)
    (proj / "02_stems" / "instrumental.wav").write_bytes(b"\x00" * 4096)

    fake_run, _ = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())

    assert state.status == "done"
    compat = proj / "02_stems" / "video.mp4.instrumental.wav"
    assert compat.exists()
    assert compat.read_bytes() == (proj / "02_stems" / "instrumental.wav").read_bytes()


def test_run_passes_vocal_gain_and_inst_gain_from_config(tmp_path, monkeypatch):
    """vocal_gain and inst_gain are user-tunable dB values from
    config.defaults; they must be threaded through verbatim.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(vocal_gain=6.0, inst_gain=-1.5))
    AssembleStage().run(proj, cfg)

    remix_call = [c for c in calls if "dubbing_remix" in c["cmd"][1]][0]
    cmd = remix_call["cmd"]
    assert cmd[8:10] == ["--vocal-gain", "6.0"]
    assert cmd[10:12] == ["--inst-gain", "-1.5"]


# ── run() time-aligned loudnorm-builder pre-req ──────────────────────────────


def test_run_builds_time_aligned_normalized_wav_when_missing(tmp_path, monkeypatch):
    """When tts_normalized.wav is absent, the stage must invoke the canonical
    dubbing_assemble_loudnorm.py with --save-normalized-wav so cues are placed
    at their absolute timestamps from translated SRT.
    """
    proj = _make_project(tmp_path)
    # Don't pre-populate tts_normalized.wav — let the stage produce it.

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "done"

    builder_calls = [
        c for c in calls
        if any("dubbing_assemble_loudnorm" in str(x) for x in c["cmd"])
    ]
    assert len(builder_calls) == 1, "time-aligned loudnorm builder must run once"
    cmd = builder_calls[0]["cmd"]
    assert cmd[0] == "python3"
    assert any("dubbing_assemble_loudnorm.py" in str(x) for x in cmd)
    assert "--save-normalized-wav" in cmd
    save_idx = cmd.index("--save-normalized-wav")
    assert cmd[save_idx + 1] == str(proj / "06_tts_wav" / "tts_normalized.wav")
    assert "--zh-srt" in cmd
    zh_idx = cmd.index("--zh-srt")
    assert cmd[zh_idx + 1] == str(proj / "05_translated_srt" / "video.zhtw.srt")


def test_run_skips_time_aligned_builder_when_normalized_already_exists(tmp_path, monkeypatch):
    """tts_normalized.wav is the idempotency token for Step 1. If it already
    exists we must not rebuild the time-aligned fulltrack/normalized wav.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    AssembleStage().run(proj, DubConfig())

    builder_calls = [
        c for c in calls
        if any("dubbing_assemble_loudnorm" in str(x) for x in c["cmd"])
    ]
    assert builder_calls == [], "must not rebuild when tts_normalized exists"


def test_run_fails_when_time_aligned_builder_fails(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    fake_run, _ = _record_subprocess(proj, step1_returncode=1)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "time-aligned loudnorm builder exit 1" in (state.error or "")


def test_run_fails_when_builder_exits_zero_but_normalized_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    fake_run, _ = _record_subprocess(proj, step1_returncode=0, step1_should_write_normalized=False)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "produced no/empty normalized wav" in (state.error or "")


# ── run() remix failure semantics ────────────────────────────────────────────


def test_run_fails_on_remix_nonzero_exit(tmp_path, monkeypatch):
    """remix exit != 0 → stage failed. No mp4 should be left behind in
    07_final/ as a half-truth.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, _ = _record_subprocess(
        proj, remix_should_write=False, remix_returncode=1
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "remix exit 1" in (state.error or "")
    # The legacy alias must NOT have been written (we never reached step 3).
    assert not (proj / "07_final" / "video_dubbed.mp4").exists()


def test_run_fails_when_remix_exits_zero_but_stem_missing(tmp_path, monkeypatch):
    """Defensive check: a remix script that lies about success (exit 0 but
    no mp4) must still fail the stage. This matches the > 1000 byte gate
    T2/T3 use for ref/tts wavs.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, _ = _record_subprocess(
        proj, remix_should_write=False, remix_returncode=0
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "missing or too small" in (state.error or "")


def test_run_fails_when_remix_writes_placeholder_mp4(tmp_path, monkeypatch):
    """A 200-byte stem is not real. The is_done byte-size gate and the
    post-flight gate must agree, otherwise a re-run will silently skip.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    # Manually override the fake to write a stub mp4.
    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        cmd_strs = [str(x) for x in cmd]
        if any("dubbing_remix" in s for s in cmd_strs):
            out_idx = cmd_strs.index("--output")
            Path(cmd_strs[out_idx + 1]).write_bytes(b"x")
            return DummyResult(0)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "missing or too small" in (state.error or "")


def test_run_unlinks_stale_stem_before_remix(tmp_path, monkeypatch):
    """A stale stem from a previous run must be unlinked before remix
    so a silently-broken remix can't be mistaken for a successful one.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    (proj / "07_final").mkdir(parents=True, exist_ok=True)
    stale = proj / "07_final" / "video_dubbed_stem.mp4"
    stale.write_bytes(b"old")

    # Remix "succeeds" but writes a tiny placeholder (so post-flight fails).
    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        cmd_strs = [str(x) for x in cmd]
        if any("dubbing_remix" in s for s in cmd_strs):
            out_idx = cmd_strs.index("--output")
            Path(cmd_strs[out_idx + 1]).write_bytes(b"x")
            return DummyResult(0)
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    # The stale file MUST have been unlinked before remix ran, so the
    # post-flight check sees the new (tiny) output, not the old one.
    assert stale.exists()
    assert stale.stat().st_size == 1


# ── run() pre-flight failures ─────────────────────────────────────────────────


def test_run_fails_when_source_video_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "01_raw_video" / "video.mp4").unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when source video missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "source video missing" in (state.error or "")


def test_run_fails_when_no_tts_wavs(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    # Empty the tts dir entirely
    for f in (proj / "06_tts_wav").iterdir():
        f.unlink()

    def fake_run(*a, **kw):
        raise AssertionError("subprocess.run should not be called when no TTS wavs")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "failed"
    assert "no TTS wavs" in (state.error or "")


def test_run_fails_when_loudnorm_script_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)

    cfg = DubConfig()
    empty_skills = tmp_path / "empty-skills"
    empty_skills.mkdir()
    cfg.paths.skills_dir = empty_skills

    state = AssembleStage().run(proj, cfg)
    assert state.status == "failed"
    assert "loudnorm script not found" in (state.error or "")


def test_run_fails_when_remix_script_missing(tmp_path, monkeypatch):
    """If config.paths.skills_dir doesn't have dubbing_remix.py, fail fast
    with a clear error before shelling out.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "dubbing_assemble_loudnorm.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    cfg = DubConfig()
    cfg.paths.skills_dir = skills_dir

    state = AssembleStage().run(proj, cfg)
    assert state.status == "failed"
    assert "remix script not found" in (state.error or "")


# ── run() legacy alias + artifacts ───────────────────────────────────────────


def test_run_copies_legacy_alias_to_video_dubbed_mp4(tmp_path, monkeypatch):
    """video_dubbed.mp4 is the legacy compatibility shim. After the stem
    is produced, the stage must cp it to the legacy path.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, _ = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "done"
    assert (proj / "07_final" / "video_dubbed.mp4").exists()
    assert (proj / "07_final" / "video_dubbed.mp4").stat().st_size > 1000


def test_run_skips_legacy_copy_when_alias_already_exists(tmp_path, monkeypatch):
    """The legacy alias is regenerated only if missing/stale; an existing
    valid alias is left alone (cheap optimization for resume flows).
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    (proj / "07_final").mkdir(parents=True, exist_ok=True)
    legacy = proj / "07_final" / "video_dubbed.mp4"
    legacy.write_bytes(b"\x00" * 4096)
    sentinel_mtime = legacy.stat().st_mtime

    fake_run, _ = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    AssembleStage().run(proj, DubConfig())
    # mtime should be untouched (we didn't rewrite)
    assert legacy.stat().st_mtime == sentinel_mtime


def test_run_reports_artifacts_and_output_dir(tmp_path, monkeypatch):
    """state.artifacts must list the canonical stem + legacy alias (no
    fulltrack when keep_fulltrack is off). state.output_dir is 07_final.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, _ = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())
    assert state.status == "done"
    assert sorted(state.artifacts) == ["video_dubbed.mp4", "video_dubbed_stem.mp4"]
    assert state.output_dir == "07_final"


# ── run() keep_fulltrack=True branch ─────────────────────────────────────────


def test_run_invokes_loudnorm_fulltrack_when_keep_fulltrack_true(tmp_path, monkeypatch):
    """keep_fulltrack=True: run dubbing_assemble_loudnorm.py to produce
    07_final/video_dubbed_fulltrack.mp4 in addition to the stem.
    """
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(keep_fulltrack=True))
    state = AssembleStage().run(proj, cfg)

    assert state.status == "done"
    builder_calls = [
        c for c in calls
        if any("dubbing_assemble_loudnorm" in str(x) for x in c["cmd"])
    ]
    assert len(builder_calls) == 1, "time-aligned loudnorm builder must be invoked once"
    cmd = builder_calls[0]["cmd"]
    # [python3, <script>, --video, <mp4>, --zh-srt, <srt>,
    #  --tts-dir, <tts_dir>, --output, <fulltrack.mp4>]
    assert cmd[0] == "python3"
    assert cmd[1] == str(cfg.paths.skills_dir / "dubbing_assemble_loudnorm.py")
    assert cmd[2:4] == ["--video", str(proj / "01_raw_video" / "video.mp4")]
    assert cmd[4:6] == ["--zh-srt", str(proj / "05_translated_srt" / "video.zhtw.srt")]
    assert cmd[6:8] == ["--tts-dir", str(proj / "06_tts_wav")]
    assert cmd[8:10] == ["--output", str(proj / "07_final" / "video_dubbed_fulltrack.mp4")]
    assert cmd[10:12] == ["--save-normalized-wav", str(proj / "06_tts_wav" / "tts_normalized.wav")]
    # artifacts include all three mp4s
    assert sorted(state.artifacts) == [
        "video_dubbed.mp4",
        "video_dubbed_fulltrack.mp4",
        "video_dubbed_stem.mp4",
    ]


def test_run_skips_loudnorm_fulltrack_when_keep_fulltrack_false(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(keep_fulltrack=False))
    AssembleStage().run(proj, cfg)

    builder_calls = [
        c for c in calls
        if any("dubbing_assemble_loudnorm" in str(x) for x in c["cmd"])
    ]
    assert builder_calls == [], "builder must NOT run when normalized wav already exists"


def test_run_fails_when_keep_fulltrack_true_but_zh_srt_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    (proj / "05_translated_srt" / "video.zhtw.srt").unlink()

    fake_run, _ = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(keep_fulltrack=True))
    state = AssembleStage().run(proj, cfg)
    assert state.status == "failed"
    assert "translated zh SRT missing" in (state.error or "")


def test_run_fails_on_loudnorm_nonzero_exit(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    fake_run, _ = _record_subprocess(proj, step1_returncode=3)
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(keep_fulltrack=True))
    state = AssembleStage().run(proj, cfg)
    assert state.status == "failed"
    assert "time-aligned loudnorm builder exit 3" in (state.error or "")


def test_run_fails_when_loudnorm_exits_zero_but_fulltrack_missing(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    (proj / "06_tts_wav" / "tts_normalized.wav").write_bytes(b"\x00" * 4096)
    fake_run, _ = _record_subprocess(
        proj, loudnorm_should_write=False, step1_returncode=0
    )
    monkeypatch.setattr(subprocess, "run", fake_run)

    cfg = DubConfig(defaults=DefaultsConfig(keep_fulltrack=True))
    state = AssembleStage().run(proj, cfg)
    assert state.status == "failed"
    assert "video_dubbed_fulltrack.mp4 missing or too small" in (state.error or "")


# ── run() full happy path integration with mocked subprocess ─────────────────


def test_run_full_happy_path_produces_all_expected_artifacts(tmp_path, monkeypatch):
    """End-to-end happy path: TTS concat/loudnorm runs, then remix,
    then legacy alias copy. Final state should be done with stem + alias.
    """
    proj = _make_project(tmp_path)
    # Don't pre-populate tts_normalized — exercise the full Step 1 path.

    fake_run, calls = _record_subprocess(proj)
    monkeypatch.setattr(subprocess, "run", fake_run)

    state = AssembleStage().run(proj, DubConfig())

    assert state.status == "done"
    # All four expected files exist with real bytes
    stem = proj / "07_final" / "video_dubbed_stem.mp4"
    legacy = proj / "07_final" / "video_dubbed.mp4"
    normalized = proj / "06_tts_wav" / "tts_normalized.wav"
    assert stem.exists() and stem.stat().st_size > 1000
    assert legacy.exists() and legacy.stat().st_size > 1000
    assert normalized.exists() and normalized.stat().st_size > 1000
    # The pipeline invoked each external process exactly once
    assert sum(1 for c in calls if any("dubbing_assemble_loudnorm" in str(x) for x in c["cmd"])) == 1
    assert sum(1 for c in calls if any("dubbing_remix" in str(x) for x in c["cmd"])) == 1
    # Step 1 log file is written
    assert (proj / ".dub" / "06_assemble_step1_tts.log").exists()
    # Step 2 (remix) log file is written
    assert (proj / ".dub" / "06_assemble_remix.log").exists()
