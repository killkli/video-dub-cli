"""Repo-owned runtime path helpers.

These helpers centralize where pipeline wrapper scripts live during the
standalone consolidation. Production defaults to this repo's vendored
``vendor/pipeline_scripts``. Test harnesses may opt in to a different
wrapper directory via ``DUB_PIPELINE_SCRIPTS_DIR``.
"""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path


_PIPELINE_SCRIPTS_ENV = "DUB_PIPELINE_SCRIPTS_DIR"


def repo_root() -> Path:
    pkg_dir = Path(str(resources.files("dub")))
    return pkg_dir.parents[1]


def pipeline_scripts_dir() -> Path:
    override = os.environ.get(_PIPELINE_SCRIPTS_ENV)
    if override:
        return Path(override)
    return repo_root() / "vendor" / "pipeline_scripts"


def pipeline_script(name: str) -> Path:
    return pipeline_scripts_dir() / name


__all__ = [
    "repo_root",
    "pipeline_scripts_dir",
    "pipeline_script",
    "_PIPELINE_SCRIPTS_ENV",
]
