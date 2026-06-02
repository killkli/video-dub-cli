"""state.py — project state load/save/mutate for .dub/state.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dub.config import DubConfig
from dub.errors import UserError

SCHEMA_VERSION = 1
STAGE_NAMES = ["01_stems", "02_asr", "03_ref_audio", "04_translate", "05_tts", "06_assemble"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def new_state(project_dir: Path, config: DubConfig) -> dict[str, Any]:
    """Build a fresh state dict for a new project."""
    stages = {}
    for name in STAGE_NAMES:
        stages[name] = {
            "status": "pending",
            "attempts": 0,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_dir.name,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "input": {
            "video_path": "",
            "video_sha256": "",
            "duration_sec": 0.0,
            "source_lang": config.defaults.source_lang,
            "target_lang": config.defaults.target_lang,
        },
        "stages": stages,
        "config_snapshot": {},
    }


def load_state(project_dir: Path) -> dict[str, Any] | None:
    """Load state.json or return None if absent/corrupt."""
    path = project_dir / ".dub" / "state.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            raw = json.load(f)
        # Detect running stages that didn't finish — treat as pending on resume
        for name, sdata in raw.get("stages", {}).items():
            if sdata.get("status") == "running":
                sdata["status"] = "pending"
        return raw
    except (json.JSONDecodeError, OSError) as e:
        raise UserError(f"Failed to load state.json: {e}") from e


def save_state(project_dir: Path, state: dict[str, Any]) -> None:
    """Atomically write state.json."""
    path = project_dir / ".dub"
    path.mkdir(parents=True, exist_ok=True)
    tmp = path / f"state.json.tmp-{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.rename(path / "state.json")


import os  # local import to avoid polluting module-level