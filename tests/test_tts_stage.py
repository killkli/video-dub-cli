from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from dub.config import DubConfig
from dub.stages.tts import TtsStage


def test_tts_stage_uses_ja_route_for_japanese_source(tmp_path):
    proj = _make_project(tmp_path, cues=1)
    cfg = _cfg_with_fake_script(tmp_path)
    cfg.defaults.source_lang = "ja"

    script, src_flag, needs_project_dir, py, backend_name = TtsStage()._resolve_route(cfg)

    assert script.name == "runner.py"
    assert script.parent.name == "voxcpme"
    assert script.exists()
    assert src_flag == "--ja-srt"
    assert needs_project_dir is True
    assert py.name
    assert backend_name == "voxcpme"


class DummyResult:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode


def _make_project(tmp_path: Path, cues: int = 3) -> Path:
    proj = tmp_path / "proj"
    for rel in ["03_asr", "04_ref_audio", "05_translated_srt", "06_tts_wav", ".dub"]:
        (proj / rel).mkdir(parents=True, exist_ok=True)

    asr_blocks = []
    zh_blocks = []
    for i in range(1, cues + 1):
        asr_blocks.append(f"{i}\n00:00:0{i-1},000 --> 00:00:0{i},000\nHello {i}\n")
        zh_blocks.append(f"{i}\n00:00:0{i-1},000 --> 00:00:0{i},000\n哈囉 {i}\n")
        (proj / "04_ref_audio" / f"line_{i}_ref.wav").write_bytes(b"\\x00" * 4096)

    (proj / "03_asr" / "video.srt").write_text("\n".join(asr_blocks), encoding="utf-8")
    (proj / "05_translated_srt" / "video.zhtw.srt").write_text("\n".join(zh_blocks), encoding="utf-8")
    return proj


def _cfg_with_fake_script(tmp_path: Path) -> DubConfig:
    script = tmp_path / "dubbing_batch_tts.py"
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    cfg = DubConfig()
    cfg.paths.skills_dir = tmp_path
    cfg.paths.omnivoice_python = Path("/usr/bin/python3")
    cfg.defaults.source_lang = "en"
    return cfg


def test_tts_stage_waits_for_delayed_artifacts_after_subprocess_returns(tmp_path, monkeypatch):
    proj = _make_project(tmp_path, cues=3)
    cfg = _cfg_with_fake_script(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        out_dir = proj / "06_tts_wav"

        def delayed_writer():
            time.sleep(0.2)
            for i in range(1, 4):
                (out_dir / f"line_{i}_tts.wav").write_bytes(b"\\x00" * 4096)

        threading.Thread(target=delayed_writer, daemon=True).start()
        return DummyResult(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "done"
    assert sorted(state.artifacts) == [
        "line_1_tts.wav",
        "line_2_tts.wav",
        "line_3_tts.wav",
    ]


def test_tts_stage_fails_when_artifacts_never_arrive(tmp_path, monkeypatch):
    proj = _make_project(tmp_path, cues=2)
    cfg = _cfg_with_fake_script(tmp_path)

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: DummyResult(0))

    state = TtsStage().run(proj, cfg)

    assert state.status == "failed"
    assert "produced 0/2 tts wavs" in (state.error or "")


def test_tts_stage_accepts_run_when_subprocess_reports_failure_but_artifacts_complete(
    tmp_path, monkeypatch
):
    """Regression: OmniVoice / VoxCPM scripts ``sys.exit(1)`` whenever their
    own tally reports ``fail > 0 or empty > 0`` (see
    ``vendor/pipeline_scripts/dubbing_batch_tts.py:297``), but a 32-cue run
    where the script reports 31/32 ok still has 31 valid wavs on disk. The
    stage's source of truth for "done" is the post-flight check on the
    artifacts, not the script's exit code. The dub-cli stage must therefore
    declare success when every expected ``line_<i>_tts.wav`` is on disk,
    regardless of the script's own non-zero return.

    Before the fix, the stage treated any non-zero rc as a hard failure
    and returned before the per-line recovery path could run, marking
    the pipeline as failed even though 31/32 wavs were already valid
    and ready for downstream stages.
    """
    proj = _make_project(tmp_path, cues=3)
    cfg = _cfg_with_fake_script(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        out_dir = proj / "06_tts_wav"
        for i in range(1, 4):
            (out_dir / f"line_{i}_tts.wav").write_bytes(b"\x00" * 4096)
        # Script's self-tally says "Done: 2 ok, 1 failed" — exits 1.
        # But every expected wav is on disk and > _TTS_MIN_BYTES.
        return DummyResult(1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "done", (
        f"stage must accept the run when artifacts are complete, "
        f"got status={state.status!r} error={state.error!r}"
    )
    assert sorted(state.artifacts) == [
        "line_1_tts.wav",
        "line_2_tts.wav",
        "line_3_tts.wav",
    ]


def test_tts_stage_fails_when_subprocess_fails_and_recovery_cannot_fill_gap(
    tmp_path, monkeypatch
):
    """Negative case for the rc-is-advisory fix: when the subprocess
    returns non-zero AND the per-line recovery pass ALSO can't materialize
    a missing cue, the stage must still surface the failure with the
    still-missing names. The rc is no longer a hard short-circuit, but it
    is still surfaced via the standard "produced X/N" error path.
    """
    proj = _make_project(tmp_path, cues=3)
    cfg = _cfg_with_fake_script(tmp_path)

    def fake_run(cmd, stdout=None, stderr=None, text=None, check=None, **kwargs):
        out_dir = proj / "06_tts_wav"
        is_recovery = "--start" in cmd and "--end" in cmd
        if is_recovery:
            # Recovery also fails (the script is genuinely broken).
            return DummyResult(1)
        # Initial run: only line_1 materializes, then crashes (rc=1).
        (out_dir / "line_1_tts.wav").write_bytes(b"\x00" * 4096)
        return DummyResult(1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    state = TtsStage().run(proj, cfg)

    assert state.status == "failed", (
        f"expected status=failed when rc!=0 and recovery can't fill the gap, "
        f"got {state.status!r}"
    )
    # The error must name the cues that never materialized.
    assert "line_2_tts.wav" in (state.error or ""), (
        f"error must name missing line_2_tts.wav: {state.error!r}"
    )
    assert "line_3_tts.wav" in (state.error or ""), (
        f"error must name missing line_3_tts.wav: {state.error!r}"
    )
