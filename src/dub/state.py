"""State schema for video-dub-cli projects."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel


class StageState(BaseModel):
    """State for a single pipeline stage."""

    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    attempts: int = 0
    artifacts: list[str] = []
    output_dir: Optional[str] = None
    error: Optional[str] = None
    progress: Optional[dict] = None


class ProjectState(BaseModel):
    """Full project state snapshot."""

    schema_version: int = 1
    project_id: str
    created_at: str
    updated_at: str
    input: dict
    stages: dict[str, StageState]
    config_snapshot: dict


def load_state(project_dir: Path) -> ProjectState:
    """Load state.json from project_dir/.dub/."""
    state_path = project_dir / ".dub" / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"No state.json in {project_dir}")
    import json
    with open(state_path) as f:
        data = json.load(f)
    return ProjectState.model_validate(data)


def save_state(project_dir: Path, state: ProjectState) -> None:
    """Atomically save state.json via tmp+rename."""
    import json, tempfile, os

    dub_dir = project_dir / ".dub"
    dub_dir.mkdir(exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json.tmp", dir=str(dub_dir))
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(state.model_dump_json(indent=2))
        os.rename(tmp_path, str(dub_dir / "state.json"))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def reset_running_to_pending(state: ProjectState) -> None:
    """Reset all 'running' stages to 'pending' for safe resume."""
    for s in state.stages.values():
        if s.status == "running":
            s.status = "pending"