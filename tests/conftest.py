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
    fake_bin = tmp_path / "bin"
    fake_scripts = tmp_path / "scripts"
    fake_root = tmp_path / "dub-root"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_scripts.mkdir(parents=True, exist_ok=True)
    fake_root.mkdir(parents=True, exist_ok=True)

    for rel in [
        fake_bin / "qwenasr-mlx",
        fake_bin / "omnivoice-python",
        fake_scripts / "subtitle_translation.py",
        fake_scripts / "dubbing_extract_ref.py",
        fake_scripts / "dubbing_assemble_loudnorm.py",
        fake_scripts / "dubbing_remix.py",
    ]:
        rel.write_text("#!/usr/bin/env python3\n")

    content = f"""
paths:
  qwenasr_cli: {fake_bin / 'qwenasr-mlx'}
  omnivoice_python: {fake_bin / 'omnivoice-python'}
  skills_dir: {fake_scripts}
  dub_root: {fake_root}
  translation_skill: {fake_scripts / 'subtitle_translation.py'}

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