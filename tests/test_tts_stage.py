from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from dub.config import DubConfig
from dub.stages.tts import TtsStage


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
