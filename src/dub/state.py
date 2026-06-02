"""state.py — project state models and load/save helpers for .dub/state.json."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from dub.config import DubConfig
from dub.errors import UserError

SCHEMA_VERSION = 1
STAGE_NAMES = ["01_stems", "02_asr", "03_ref_audio", "04_translate", "05_tts", "06_assemble"]


class StageState(BaseModel):
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    attempts: int = 0
    artifacts: list[str] = Field(default_factory=list)
    output_dir: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    project_id: str
    created_at: str
    updated_at: str
    input: dict[str, Any] = Field(default_factory=dict)
    stages: dict[str, StageState] = Field(default_factory=dict)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(project_dir: Path, config: DubConfig) -> ProjectState:
    """Build a fresh ProjectState for a new project."""
    stages = {name: StageState() for name in STAGE_NAMES}
    return ProjectState(
        schema_version=SCHEMA_VERSION,
        project_id=project_dir.name,
        created_at=now_iso(),
        updated_at=now_iso(),
        input={
            "video_path": "",
            "video_sha256": "",
            "duration_sec": 0.0,
            "source_lang": config.defaults.source_lang,
            "target_lang": config.defaults.target_lang,
        },
        stages=stages,
        config_snapshot={},
    )


def reset_running_to_pending(state: ProjectState) -> ProjectState:
    """Convert any in-flight stage back to pending for resume semantics."""
    for stage in state.stages.values():
        if stage.status == "running":
            stage.status = "pending"
            stage.started_at = None
    state.updated_at = now_iso()
    return state


def load_state(project_dir: Path) -> ProjectState:
    """Load .dub/state.json without mutating in-flight stage status."""
    path = project_dir / ".dub" / "state.json"
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        raw = json.loads(path.read_text())
        return ProjectState.model_validate(raw)
    except FileNotFoundError:
        raise
    except Exception as e:
        raise UserError(f"Failed to load state.json: {e}") from e


def save_state(project_dir: Path, state: ProjectState | dict[str, Any]) -> None:
    """Atomically write .dub/state.json."""
    if isinstance(state, ProjectState):
        state_obj = state
    else:
        payload = {
            "schema_version": state.get("schema_version", SCHEMA_VERSION),
            "project_id": state.get("project_id", project_dir.name),
            "created_at": state.get("created_at", now_iso()),
            "updated_at": state.get("updated_at", now_iso()),
            "input": state.get("input", {}),
            "stages": state.get("stages", {}),
            "config_snapshot": state.get("config_snapshot", {}),
        }
        state_obj = ProjectState.model_validate(payload)
    state_obj.updated_at = now_iso()

    dotdub = project_dir / ".dub"
    dotdub.mkdir(parents=True, exist_ok=True)
    tmp = dotdub / f"state.json.tmp-{os.getpid()}"
    tmp.write_text(json.dumps(state_obj.to_dict(), indent=2, ensure_ascii=False))
    tmp.replace(dotdub / "state.json")


__all__ = [
    "SCHEMA_VERSION",
    "STAGE_NAMES",
    "StageState",
    "ProjectState",
    "now_iso",
    "new_state",
    "reset_running_to_pending",
    "load_state",
    "save_state",
]
