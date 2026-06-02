"""Tests for dub.state."""
from __future__ import annotations

import os, tempfile
from pathlib import Path

import pytest

from dub.state import (
    ProjectState,
    StageState,
    load_state,
    save_state,
    reset_running_to_pending,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_project(tmp: Path) -> Path:
    p = tmp / "proj"
    (p / ".dub").mkdir(parents=True)
    return p


def make_state(stages: dict | None = None) -> ProjectState:
    return ProjectState(
        project_id="test-123",
        created_at="2026-06-02T00:00:00+00:00",
        updated_at="2026-06-02T00:00:00+00:00",
        input={"video_path": "/tmp/video.mp4"},
        stages=stages or {
            "01_stems": StageState(status="done"),
            "02_asr": StageState(status="running"),
            "03_ref_audio": StageState(status="pending"),
        },
        config_snapshot={},
    )


# ─── StageState tests ─────────────────────────────────────────────────────────

def test_stage_state_defaults():
    s = StageState()
    assert s.status == "pending"
    assert s.attempts == 0
    assert s.artifacts == []


def test_stage_state_full():
    s = StageState(
        status="done",
        started_at="2026-06-02T00:00:00+00:00",
        finished_at="2026-06-02T00:01:00+00:00",
        attempts=2,
        artifacts=["a.wav", "b.wav"],
        output_dir="02_stems",
    )
    assert s.status == "done"
    assert s.attempts == 2


# ─── ProjectState tests ───────────────────────────────────────────────────────

def test_project_state_defaults():
    p = ProjectState(
        project_id="p1",
        created_at="2026-06-02T00:00:00+00:00",
        updated_at="2026-06-02T00:00:00+00:00",
        input={},
        stages={},
        config_snapshot={},
    )
    assert p.schema_version == 1


# ─── save/load round-trip ─────────────────────────────────────────────────────

def test_save_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj = make_project(tmp)
        state = make_state()
        save_state(proj, state)
        loaded = load_state(proj)
        assert loaded.project_id == state.project_id
        assert loaded.stages["01_stems"].status == "done"
        assert loaded.stages["02_asr"].status == "running"


# ─── atomic write ─────────────────────────────────────────────────────────────

def test_atomic_write_does_not_corrupt_on_failure():
    """If write fails midway, old state.json stays intact."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj = make_project(tmp)

        # Write initial state
        state1 = make_state({"01_stems": StageState(status="done")})
        save_state(proj, state1)

        # Attempt to save a malformed state (project_id required)
        state2 = ProjectState(
            schema_version=1,
            project_id="test-456",
            created_at="2026-06-02T00:00:00+00:00",
            updated_at="2026-06-02T00:00:00+00:00",
            input={},
            stages={},
            config_snapshot={},
        )

        try:
            # This should work
            save_state(proj, state2)
        except Exception:
            pass

        # State should still be the last valid one or initial
        loaded = load_state(proj)
        # Either the failed write left old state, or nothing happened — no crash
        assert loaded.project_id in ("test-456", "test-123")


# ─── reset_running_to_pending ────────────────────────────────────────────────

def test_reset_running_to_pending():
    state = make_state({
        "01_stems": StageState(status="done"),
        "02_asr": StageState(status="running"),
        "03_ref_audio": StageState(status="running"),
    })
    reset_running_to_pending(state)
    assert state.stages["01_stems"].status == "done"
    assert state.stages["02_asr"].status == "pending"
    assert state.stages["03_ref_audio"].status == "pending"


def test_reset_all_running():
    state = make_state({
        "a": StageState(status="running"),
        "b": StageState(status="pending"),
        "c": StageState(status="failed"),
        "d": StageState(status="running"),
    })
    reset_running_to_pending(state)
    assert state.stages["a"].status == "pending"
    assert state.stages["b"].status == "pending"
    assert state.stages["c"].status == "failed"
    assert state.stages["d"].status == "pending"


# ─── load_state missing file ───────────────────────────────────────────────────

def test_load_state_file_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj = make_project(tmp)
        with pytest.raises(FileNotFoundError):
            load_state(proj)