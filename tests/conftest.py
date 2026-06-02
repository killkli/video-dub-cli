"""Shared pytest fixtures."""
from __future__ import annotations

import sys, tempfile
from pathlib import Path

import pytest

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def tmp_path(tmp_path_factory):
    """Provide a temporary directory as Path (pytest's tmp_path is already Path)."""
    return tmp_path_factory.mktemp("dub")


@pytest.fixture
def minimal_config_yaml(tmp_path):
    """A minimal valid YAML config with all required paths."""
    content = """
paths:
  qwenasr_cli: /path/to/qwenasr-mlx
  omnivoice_python: /path/to/omnivoice-python
  skills_dir: /path/to/video-dubbing-pipeline/scripts
  dub_root: ~/.hermes
  translation_skill: /path/to/subtitle_translation.py

defaults:
  source_lang: en
  target_lang: zh
  vocal_gain: 3.0
  inst_gain: -3.0
  keep_fulltrack: false

retry:
  max_attempts: 3
  backoff_seconds: 5.0
  retry_on:
    - subprocess.CalledProcessError
    - TimeoutError
    - ConnectionError

logging:
  level: INFO
  json_logs: false
  progress: rich
"""
    p = tmp_path / "config.yaml"
    p.write_text(content)
    return p