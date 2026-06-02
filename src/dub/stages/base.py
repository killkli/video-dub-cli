"""stages/base.py — abstract base class for all pipeline stages."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StageState:
    """Mutable result returned by each stage's run()."""
    name: str
    status: str = "pending"          # pending|running|done|failed|skipped
    started_at: str = ""
    finished_at: str = ""
    attempts: int = 0
    error: str = ""
    artifacts: list[str] = field(default_factory=list)
    output_dir: str = ""
    progress: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "attempts": self.attempts,
            "error": self.error,
            "artifacts": self.artifacts,
            "output_dir": self.output_dir,
            "progress": self.progress,
        }


class Stage(ABC):
    """Abstract base for all pipeline stages."""

    # Subclass fills this in, e.g. "01_stems", "02_asr"
    name: str = ""

    @abstractmethod
    def is_done(self, project_dir: Path) -> bool:
        """Return True if this stage's outputs already exist (skip-existing)."""

    @abstractmethod
    def run(self, project_dir: Path, config: Any) -> StageState:
        """Execute the stage. May raise subprocess.CalledProcessError / TimeoutError."""