"""Repo-owned runtime path helpers.

These helpers centralize where pipeline wrapper scripts live during the
standalone consolidation. Callers should prefer these functions over
reaching into legacy config names like ``skills_dir`` directly.
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path


def repo_root() -> Path:
    pkg_dir = Path(str(resources.files("dub")))
    return pkg_dir.parents[1]


def pipeline_scripts_dir() -> Path:
    return repo_root() / "vendor" / "pipeline_scripts"


def pipeline_script(name: str) -> Path:
    return pipeline_scripts_dir() / name


__all__ = ["repo_root", "pipeline_scripts_dir", "pipeline_script"]
