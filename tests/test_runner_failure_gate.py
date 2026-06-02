from __future__ import annotations

from pathlib import Path

import pytest

from dub.config import DubConfig
from dub.runner import run_pipeline
from dub.stages.base import Stage, StageState
from dub.state import now_iso, new_state, save_state


class _DoneStage(Stage):
    def __init__(self, name: str):
        self.name = name

    def is_done(self, project_dir: Path) -> bool:
        return False

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        return StageState(
            status="done",
            started_at=now_iso(),
            finished_at=now_iso(),
            attempts=1,
            artifacts=[f"{self.name}.txt"],
            output_dir="out",
        )


class _FailedReturnStage(Stage):
    name = "02_asr"

    def is_done(self, project_dir: Path) -> bool:
        return False

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        return StageState(
            status="failed",
            started_at=now_iso(),
            finished_at=now_iso(),
            attempts=1,
            error="synthetic stage failure",
        )


def test_run_pipeline_hard_stops_when_stage_returns_failed_state(tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / ".dub").mkdir()
    save_state(project_dir, new_state(project_dir, DubConfig()))

    fake_stages = [
        _DoneStage("01_stems"),
        _FailedReturnStage(),
        _DoneStage("03_ref_audio"),
        _DoneStage("04_translate"),
        _DoneStage("05_tts"),
        _DoneStage("06_assemble"),
    ]

    monkeypatch.setattr("dub.runner.StemsStage", lambda: fake_stages[0])
    monkeypatch.setattr("dub.runner.AsrStage", lambda: fake_stages[1])
    monkeypatch.setattr("dub.runner.RefAudioStage", lambda: fake_stages[2])
    monkeypatch.setattr("dub.runner.TranslateStage", lambda: fake_stages[3])
    monkeypatch.setattr("dub.runner.TtsStage", lambda: fake_stages[4])
    monkeypatch.setattr("dub.runner.AssembleStage", lambda: fake_stages[5])

    with pytest.raises(RuntimeError, match="synthetic stage failure"):
        run_pipeline(project_dir, DubConfig())
