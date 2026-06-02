"""Regression tests for stage-05 (TTS) artifact-mismatch fix.

Rooted in the P3-T7 debug wave — the second real YouTube smoke rerun
showed the OmniVoice script logging ``Done: 32 ok, 0 failed`` while
``06_tts_wav/`` only contained 22/32 wavs. Investigation found:

  1. The OmniVoice script wrote non-atomically: ``torchaudio.save(out_wav, ...)``
     publishes the file to its final name *during* the write, so a partial
     buffer is observable on disk.
  2. The script counted "ok" by ``tts_segment()`` return value, not by the
     resulting file's size on disk. An MPS edge case in OmniVoice can
     produce an empty / near-empty tensor that the function still returns
     True for, leaving a 0-byte or near-0 wav at ``line_<i>_tts.wav``.
  3. The dub-cli stage verifier caught the discrepancy and marked the
     stage as failed — but the operator's log was the *script's* self-
     report (32/32 ok), making diagnosis hard.
  4. There was no resumability path: even after the verifier reported
     failure, a re-run had no way to fill in just the missing lines.

The fix has three legs:

  a. OmniVoice / VoxCPM scripts now write atomically (tmp + os.replace)
     and only count a line as "ok" if the on-disk file is > 1KB.
  b. Both scripts accept ``--start`` / ``--end`` so the stage can re-run
     only the missing cues.
  c. The dub-cli stage verifier now does a per-line recovery pass when
     any cue is missing: for each missing ``line_<i>_tts.wav`` it re-
     invokes the script with ``--start i --end i``, and only fails the
     stage if recovery also can't materialize the file.

These tests exercise (c) directly with a mocked subprocess that
reproduces the exact "22/32 partial" failure pattern.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest

from dub.config import DubConfig
from dub.stages.tts import TtsStage, _TTS_MIN_BYTES, _missing_tts_wavs


# ── Shared helpers ─────────────────────────────────────────────────────────


def _fmt_ts(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm. Always 2-digit fields."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _make_project(tmp_path: Path, cues: int = 3) -> Path:
    """Build the minimum project layout that satisfies the TTS pre-flight.

    Mirrors the rest of the dub-cli test suite: 03_asr / 04_ref_audio /
    05_translated_srt / 06_tts_wav / .dub with N SRT cues and N ref wavs
    sized > _TTS_MIN_BYTES (so the stage's is_done() reads them as ready).
    """
    proj = tmp_path / "proj"
    for rel in ["03_asr", "04_ref_audio", "05_translated_srt", "06_tts_wav", ".dub"]:
        (proj / rel).mkdir(parents=True, exist_ok=True)

    asr_blocks: list[str] = []
    zh_blocks: list[str] = []
    for i in range(1, cues + 1):
        start_ts = _fmt_ts(float(i - 1))
        end_ts = _fmt_ts(float(i))
        asr_blocks.append(f"{i}\n{start_ts} --> {end_ts}\nHello {i}\n")
        zh_blocks.append(f"{i}\n{start_ts} --> {end_ts}\n哈囉 {i}\n")
        (proj / "04_ref_audio" / f"line_{i}_ref.wav").write_bytes(b"\x00" * 4096)

    (proj / "03_asr" / "video.srt").write_text("\n".join(asr_blocks), encoding="utf-8")
    (proj / "05_translated_srt" / "video.zhtw.srt").write_text(
        "\n".join(zh_blocks), encoding="utf-8"
    )
    return proj


def _cfg_with_fake_script(tmp_path: Path) -> DubConfig:
    """Configure a DubConfig that points at a stub TTS script. The test
    monkey-patches ``subprocess.run`` so the stub is never actually
    executed — the script path only needs to *exist* for the stage
    pre-flight.
    """
    script = tmp_path / "dubbing_batch_tts.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    cfg = DubConfig()
    cfg.paths.skills_dir = tmp_path
    cfg.paths.omnivoice_python = Path("/usr/bin/python3")
    cfg.defaults.source_lang = "en"
    return cfg


# ── is_done() respects the size gate ───────────────────────────────────────


def test_is_done_treats_empty_files_as_missing(tmp_path):
    """A 0-byte ``line_<i>_tts.wav`` is NOT a successful TTS artifact.

    This guards against the partial-write failure mode where the OmniVoice
    script wrote a headerless / truncated file and counted it as ok.
    """
    proj = _make_project(tmp_path, cues=2)
    out = proj / "06_tts_wav"
    # Both files exist but one is empty — the exact on-disk signature
    # of the partial-write failure mode.
    (out / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
    (out / "line_2_tts.wav").write_bytes(b"")
    assert TtsStage().is_done(proj) is False


def test_is_done_false_when_just_below_threshold(tmp_path):
    """A file sized exactly _TTS_MIN_BYTES is not enough — must be > it.

    This matches the threshold the OmniVoice / VoxCPM scripts use, so
    the stage's is_done() and the scripts' skip-existing gate agree.
    """
    proj = _make_project(tmp_path, cues=1)
    out = proj / "06_tts_wav"
    (out / "line_1_tts.wav").write_bytes(b"\x00" * _TTS_MIN_BYTES)
    assert TtsStage().is_done(proj) is False
    # One byte over the threshold: it counts.
    (out / "line_1_tts.wav").write_bytes(b"\x00" * (_TTS_MIN_BYTES + 1))
    assert TtsStage().is_done(proj) is True


# ── The 22/32 reproducer ───────────────────────────────────────────────────


def _make_partial_run_subprocess(
    proj: Path, total: int, missing_indices: set[int], call_log: list[list[str]]
):
    """Build a fake ``subprocess.run`` that mirrors the 22/32 bug.

    The first invocation (no --start/--end) writes wavs for every cue
    EXCEPT those in ``missing_indices`` — these leave a 0-byte or absent
    file on disk, exactly like the original failure mode. Per-line
    recovery invocations (with --start i --end i) DO write a real wav
    for the missing cue, simulating that a fresh run of the script
    works when scoped to a single line.
    """

    def _extract_idx(cmd: list[str]) -> int | None:
        # OmniVoice: --start N --end N ; VoxCPM: --start N --end N
        for j, tok in enumerate(cmd):
            if tok == "--start" and j + 1 < len(cmd):
                try:
                    return int(cmd[j + 1])
                except ValueError:
                    return None
        return None

    def _is_recovery_call(cmd: list[str]) -> bool:
        # A recovery call carries both --start and --end pointing at the
        # same index. The initial run carries neither.
        s = _extract_idx(cmd)
        if s is None:
            return False
        for j, tok in enumerate(cmd):
            if tok == "--end" and j + 1 < len(cmd):
                try:
                    return int(cmd[j + 1]) == s
                except ValueError:
                    return False
        return False

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        call_log.append(list(cmd))
        out_dir = proj / "06_tts_wav"
        if _is_recovery_call(cmd):
            # Recovery writes the file for the requested line, always.
            idx = _extract_idx(cmd)
            assert idx is not None
            (out_dir / f"line_{idx}_tts.wav").write_bytes(b"\x00" * 4096)
            return _DummyResult(0)

        # Initial run: write everything except the missing indices, to
        # reproduce the exact 22/32 partial artifact state observed in
        # the bug report.
        for i in range(1, total + 1):
            if i in missing_indices:
                # Partial-write: leave a 0-byte placeholder. The original
                # bug was that the file APPEARED in the directory but
                # was empty (headerless / truncated).
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"")
            else:
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        return _DummyResult(0)

    return fake_run


class _DummyResult:
    def __init__(self, returncode: int):
        self.returncode = returncode


def test_stage_recovers_from_22_of_32_partial_artifact_failure(
    tmp_path, monkeypatch
):
    """The 22/32 reproducer: stage must auto-recover missing lines.

    Mock subprocess.run to (a) leave 10 of 32 lines as 0-byte placeholders
    on the first invocation, and (b) successfully write real wavs when
    called with --start i --end i. The stage's per-line recovery pass
    must fill in the 10 missing cues, and the stage must end in status
    "done" with all 32 line_*_tts.wav artifacts recorded.
    """
    total = 32
    missing = {3, 7, 11, 12, 18, 19, 22, 24, 27, 30}
    assert len(missing) == 10  # exact 22/32 case

    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)
    call_log: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run",
        _make_partial_run_subprocess(proj, total, missing, call_log),
    )

    state = TtsStage().run(proj, cfg)

    # Stage must recover. Status is "done", every line accounted for.
    assert state.status == "done", (
        f"expected recovered status=done, got {state.status!r} "
        f"error={state.error!r}"
    )
    assert len(state.artifacts) == total, (
        f"expected {total} artifacts, got {len(state.artifacts)}: "
        f"{state.artifacts}"
    )
    # The initial call is the first subprocess invocation; the recovery
    # pass issues one additional call per missing line.
    assert len(call_log) == 1 + len(missing), (
        f"expected 1 initial + {len(missing)} recovery calls, got "
        f"{len(call_log)}"
    )
    # Verify every recovered call really was scoped to a single line.
    for cmd in call_log[1:]:
        assert "--start" in cmd
        assert "--end" in cmd
        # Same start and end ⇒ single-line call.
        s_idx = cmd.index("--start")
        e_idx = cmd.index("--end")
        assert cmd[s_idx + 1] == cmd[e_idx + 1]


def test_stage_fails_when_per_line_recovery_also_fails(
    tmp_path, monkeypatch
):
    """If recovery itself can't materialize the missing lines, the stage
    must surface a clear failure with the still-missing cue names. The
    operator can then re-run with a larger TTS model, fix the script,
    or accept the partial pipeline.
    """
    total = 5
    missing = {2, 4}
    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)

    # Build a fake subprocess that fails the recovery calls too: the
    # initial run leaves 0-byte placeholders, and per-line recovery calls
    # ALSO leave the target line at 0 bytes.
    call_log: list[list[str]] = []

    def fake_run_no_recover(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        call_log.append(list(cmd))
        out_dir = proj / "06_tts_wav"
        is_recovery = "--start" in cmd and "--end" in cmd
        if is_recovery:
            idx = int(cmd[cmd.index("--start") + 1])
            (out_dir / f"line_{idx}_tts.wav").write_bytes(b"")
            return _DummyResult(0)

        for i in range(1, total + 1):
            if i in missing:
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"")
            else:
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        return _DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run_no_recover)

    state = TtsStage().run(proj, cfg)

    # Stage must surface the failure — 0-byte placeholders are NOT ok.
    assert state.status == "failed", (
        f"expected status=failed when recovery can't materialize files, "
        f"got {state.status!r}"
    )
    # The error must name the still-missing lines so the operator can
    # act on them. Both line_2_tts.wav and line_4_tts.wav should appear.
    assert "line_2_tts.wav" in (state.error or ""), (
        f"error must name missing line_2_tts.wav: {state.error!r}"
    )
    assert "line_4_tts.wav" in (state.error or ""), (
        f"error must name missing line_4_tts.wav: {state.error!r}"
    )
    # Recovery was attempted for every missing line.
    assert len(call_log) == 1 + len(missing)


def test_stage_does_not_recover_when_initial_run_is_complete(
    tmp_path, monkeypatch
):
    """Happy path: if the initial run writes all 32 lines, no per-line
    recovery calls should be issued. This guards against the recovery
    path being too eager and over-firing on every run.
    """
    total = 4
    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)
    call_log: list[list[str]] = []

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        call_log.append(list(cmd))
        out_dir = proj / "06_tts_wav"
        # Always write all lines successfully — no missing, no recovery.
        for i in range(1, total + 1):
            (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        return _DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    assert len(state.artifacts) == total
    # Only the initial call — no recovery calls issued.
    assert len(call_log) == 1


def test_stage_handles_delayed_artifact_visibility(
    tmp_path, monkeypatch
):
    """The script's atomic write means files can be slightly delayed
    after the subprocess returns. The stage's stabilization window
    must wait for them to appear (this is the original band-aid
    behavior that the resumability was layered on top of).
    """
    total = 3
    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        out_dir = proj / "06_tts_wav"

        def delayed_writer():
            time.sleep(0.3)
            for i in range(1, total + 1):
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)

        threading.Thread(target=delayed_writer, daemon=True).start()
        return _DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    assert len(state.artifacts) == total


# ── Helper unit test: _missing_tts_wavs must agree with is_done() ─────────


def test_missing_tts_wavs_agrees_with_is_done(tmp_path):
    """The helper used by the verifier's post-flight loop must classify
    a file as "missing" whenever is_done() would return False. This
    invariant is what makes the per-line recovery pass target the
    right cues.
    """
    proj = _make_project(tmp_path, cues=4)
    out = proj / "06_tts_wav"
    (out / "line_1_tts.wav").write_bytes(b"\x00" * 2048)
    (out / "line_2_tts.wav").write_bytes(b"\x00" * 2048)
    # line_3 missing
    (out / "line_4_tts.wav").write_bytes(b"\x00" * 50)  # below threshold

    missing = _missing_tts_wavs(out, expected=4)
    assert "line_3_tts.wav" in missing
    assert "line_4_tts.wav" in missing
    assert "line_1_tts.wav" not in missing
    assert "line_2_tts.wav" not in missing
    assert TtsStage().is_done(proj) is False


# ── Second-half of the bug: the production failure mode ─────────────────
# The original 22/32 incident on the real OmniVoice / MPS run had ten
# cues where the file was *entirely absent* (model.generate raised mid-
# synthesis and the atomic-write path never executed) — not a 0-byte
# placeholder. Both shapes must be detected and recovered, because the
# OmniVoice script's own "Done: 32 ok, 0 failed" line is computed from
# tts_segment()'s return value and won't reflect an unhandled raise.


def _make_partially_absent_run_subprocess(
    proj: Path, total: int, missing_indices: set[int], call_log: list[list[str]]
):
    """Build a fake ``subprocess.run`` that mirrors the original real-run
    22/32 bug: the initial run completely omits ``line_<i>_tts.wav`` for
    each cue in ``missing_indices`` (no placeholder, no 0-byte file —
    just nothing on disk). Per-line recovery calls always succeed.

    The 0-byte-placeholder shape is covered by
    ``_make_partial_run_subprocess`` above; this one is the "model
    raised, file never existed" shape.
    """

    def _extract_idx(cmd: list[str]) -> int | None:
        for j, tok in enumerate(cmd):
            if tok == "--start" and j + 1 < len(cmd):
                try:
                    return int(cmd[j + 1])
                except ValueError:
                    return None
        return None

    def _is_recovery_call(cmd: list[str]) -> bool:
        s = _extract_idx(cmd)
        if s is None:
            return False
        for j, tok in enumerate(cmd):
            if tok == "--end" and j + 1 < len(cmd):
                try:
                    return int(cmd[j + 1]) == s
                except ValueError:
                    return False
        return False

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        call_log.append(list(cmd))
        out_dir = proj / "06_tts_wav"
        if _is_recovery_call(cmd):
            idx = _extract_idx(cmd)
            assert idx is not None
            (out_dir / f"line_{idx}_tts.wav").write_bytes(b"\x00" * 4096)
            return _DummyResult(0)

        # Initial run: leave missing lines COMPLETELY ABSENT.
        for i in range(1, total + 1):
            if i in missing_indices:
                continue  # do not write anything at all for this cue
            (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        return _DummyResult(0)

    return fake_run


def test_stage_recovers_from_22_of_32_with_files_truly_absent(
    tmp_path, monkeypatch
):
    """The other half of the 22/32 reproducer: missing files are TRULY
    absent, not 0-byte placeholders. Mirrors the original OmniVoice / MPS
    failure mode where ``model.generate()`` raised mid-synthesis and the
    atomic write never executed. The stage's per-line recovery must fill
    in the missing cues exactly the same way as for 0-byte placeholders.
    """
    total = 32
    missing = {3, 7, 11, 12, 18, 19, 22, 24, 27, 30}
    assert len(missing) == 10

    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)
    call_log: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run",
        _make_partially_absent_run_subprocess(proj, total, missing, call_log),
    )

    state = TtsStage().run(proj, cfg)

    assert state.status == "done", (
        f"expected recovered status=done, got {state.status!r} "
        f"error={state.error!r}"
    )
    assert len(state.artifacts) == total, (
        f"expected {total} artifacts, got {len(state.artifacts)}: "
        f"{state.artifacts}"
    )
    # Confirm the absent-files are now real on disk (> _TTS_MIN_BYTES),
    # not placeholders.
    for idx in missing:
        wav = proj / "06_tts_wav" / f"line_{idx}_tts.wav"
        assert wav.exists()
        assert wav.stat().st_size > _TTS_MIN_BYTES
    # 1 initial call + 10 single-line recovery calls.
    assert len(call_log) == 1 + len(missing)


def test_stage_recovers_from_mixed_absent_and_zero_byte_artifacts(
    tmp_path, monkeypatch
):
    """Mixed failure shape: some missing lines are truly absent, others
    are 0-byte placeholders. A real MPS re-run may produce either shape
    depending on where in the model pipeline the failure happened.
    Recovery must treat them the same way.
    """
    total = 32
    absent = {3, 7, 11, 18, 22, 27}            # 6 lines: no file at all
    zero_byte = {12, 19, 24, 30}                # 4 lines: 0-byte placeholder
    missing = absent | zero_byte
    assert len(missing) == 10

    proj = _make_project(tmp_path, cues=total)
    cfg = _cfg_with_fake_script(tmp_path)
    call_log: list[list[str]] = []

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        call_log.append(list(cmd))
        out_dir = proj / "06_tts_wav"

        def _extract_idx(c):
            for j, tok in enumerate(c):
                if tok == "--start" and j + 1 < len(c):
                    try:
                        return int(c[j + 1])
                    except ValueError:
                        return None
            return None

        is_recovery = "--start" in cmd and "--end" in cmd
        if is_recovery:
            idx = _extract_idx(cmd)
            assert idx is not None
            (out_dir / f"line_{idx}_tts.wav").write_bytes(b"\x00" * 4096)
            return _DummyResult(0)

        for i in range(1, total + 1):
            if i in absent:
                continue
            if i in zero_byte:
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"")
            else:
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        return _DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "done", (
        f"expected recovered status=done, got {state.status!r} "
        f"error={state.error!r}"
    )
    assert len(state.artifacts) == total
    assert len(call_log) == 1 + len(missing)
