"""Tests for dub.config."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dub.config import (
    DubConfig,
    DefaultsConfig,
    load_config,
    PathsConfig,
    RetryConfig,
    LoggingConfig,
    UserError,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def write_yaml(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content)
    return p


# ─── Pydantic model tests ──────────────────────────────────────────────────────

def test_paths_config_defaults():
    p = PathsConfig(
        qwenasr_cli=Path("/bin/false"),
        omnivoice_python=Path("/bin/false"),
        skills_dir=Path("/tmp"),
        translation_skill=Path("/bin/false"),
    )
    assert p.dub_root == Path.home() / "video-dub-cli-runs"


def test_default_paths_use_repo_owned_vendor_scripts():
    cfg = load_config(None)
    assert cfg.paths.skills_dir.name == "pipeline_scripts"
    assert cfg.paths.skills_dir.parent.name == "vendor"


def test_defaults_config_defaults():
    d = DefaultsConfig()
    assert d.source_lang == "en"
    assert d.target_lang == "zh"
    assert d.vocal_gain == 3.0
    assert d.inst_gain == -3.0
    assert d.keep_fulltrack is False


def test_retry_config_defaults():
    r = RetryConfig()
    assert r.max_attempts == 3
    assert r.backoff_seconds == 5.0
    assert "subprocess.CalledProcessError" in r.retry_on


def test_logging_config_defaults():
    l = LoggingConfig()
    assert l.level == "INFO"
    assert l.json_logs is False
    assert l.file is None
    assert l.progress == "rich"


def test_dub_config_full():
    paths = PathsConfig(
        qwenasr_cli=Path("/bin/true"),
        omnivoice_python=Path("/bin/true"),
        skills_dir=Path("/tmp"),
        translation_skill=Path("/bin/true"),
    )
    cfg = DubConfig(paths=paths)
    assert cfg.defaults is not None
    assert cfg.translation.provider == "gemini"
    assert cfg.retry is not None
    assert cfg.logging is not None


def test_paths_config_can_be_constructed_with_repo_defaults():
    p = PathsConfig()
    # qwenasr_cli is a legacy optional field (the ASR stage is now repo-owned);
    # the default is None, not a bare CLI name.
    assert p.qwenasr_cli is None
    assert p.skills_dir.name == "pipeline_scripts"
    assert p.tts_engines_dir.name == "pipeline_scripts"
    # New test-only ASR escape hatches default to off.
    assert p.asr_test_fixture_srt is None
    assert p.asr_test_backend_fail is False


# ─── load_config tests ──────────────────────────────────────────────────────────

def test_load_config_from_yaml_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path = write_yaml(tmp, "config.yaml", """
paths:
  qwenasr_cli: /usr/bin/true
  omnivoice_python: /usr/bin/python3
  skills_dir: /tmp/vendor/pipeline_scripts
  translation_skill: /tmp/trans.py
defaults:
  source_lang: ja
  target_lang: zh
""")
        cfg = load_config(config_path)
        assert cfg.paths.qwenasr_cli == Path("/usr/bin/true")
        assert cfg.defaults.source_lang == "ja"


def test_load_config_translation_section():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path = write_yaml(tmp, "config.yaml", """
paths:
  qwenasr_cli: /usr/bin/true
  omnivoice_python: /usr/bin/python3
  skills_dir: /tmp/vendor/pipeline_scripts
  translation_skill: /tmp/trans.py
translation:
  provider: gemini
  model: gemini-2.5-flash
  api_env_var: GEMINI_API_KEY
defaults:
  source_lang: ja
  target_lang: zh
""")
        cfg = load_config(config_path)
        assert cfg.translation.provider == "gemini"
        assert cfg.translation.model == "gemini-2.5-flash"
        assert cfg.translation.api_env_var == "GEMINI_API_KEY"


def test_load_config_accepts_yaml_without_paths_section():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        config_path = write_yaml(tmp, "no_paths.yaml", "logging:\n  level: DEBUG\n")
        cfg = load_config(config_path)
        assert cfg.logging.level == "DEBUG"
        assert cfg.paths.skills_dir.name == "pipeline_scripts"


def test_load_config_merge_user_config_over_defaults():
    """User config overrides values from default config."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        default_path = write_yaml(tmp, "default.yaml", """
paths:
  qwenasr_cli: /bin/default
  omnivoice_python: /bin/default
  skills_dir: /tmp/vendor/pipeline_scripts
  translation_skill: /tmp/trans.py
defaults:
  vocal_gain: 99.0
""")
        user_path = write_yaml(tmp, "user.yaml", """
paths:
  qwenasr_cli: /bin/user
  omnivoice_python: /bin/user
  skills_dir: /tmp/vendor/pipeline_scripts
  translation_skill: /tmp/trans.py
defaults:
  vocal_gain: 1.0
""")
        cfg = load_config(user_path)
        assert cfg.paths.qwenasr_cli == Path("/bin/user")
        assert cfg.defaults.vocal_gain == 1.0


def test_load_config_missing_paths_uses_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = write_yaml(tmp, "empty.yaml", "logging:\n  level: DEBUG\n")
        cfg = load_config(p)
        assert cfg.logging.level == "DEBUG"
        assert cfg.paths.omnivoice_python == Path("python3")