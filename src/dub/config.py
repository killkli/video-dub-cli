"""Configuration schema for video-dub-cli."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class PathsConfig(BaseModel):
    """Required paths for the dub pipeline."""

    qwenasr_cli: Path
    omnivoice_python: Path
    skills_dir: Path
    dub_root: Path = Path("~/.hermes").expanduser()
    translation_skill: Path


class DefaultsConfig(BaseModel):
    """Default pipeline parameters."""

    source_lang: Literal["en", "ja", "zh"] = "en"
    target_lang: Literal["zh", "en"] = "zh"
    vocal_gain: float = 3.0
    inst_gain: float = -3.0
    keep_fulltrack: bool = False


class RetryConfig(BaseModel):
    """Retry policy for failed subprocess calls."""

    max_attempts: int = Field(3, ge=1, le=10)
    backoff_seconds: float = 5.0
    retry_on: list[str] = [
        "subprocess.CalledProcessError",
        "TimeoutError",
        "ConnectionError",
    ]


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_logs: bool = False
    file: Optional[Path] = None
    progress: Literal["rich", "plain", "none"] = "rich"


class DubConfig(BaseModel):
    """Root configuration object."""

    paths: PathsConfig
    defaults: DefaultsConfig = DefaultsConfig()
    retry: RetryConfig = RetryConfig()
    logging: LoggingConfig = LoggingConfig()


class UserError(Exception):
    """Raised when configuration is invalid or user input is wrong."""

    pass


def load_config(path: Optional[Path] = None) -> DubConfig:
    """
    Load configuration.

    Priority (high → low):
    1. ``path`` argument
    2. ~/.config/dub/config.yaml
    3. built-in defaults

    Raises UserError if ``paths`` section is missing.
    """
    import yaml

    base = Path.home() / ".config" / "dub" / "config.yaml"

    defaults: dict = {}
    if base.exists():
        with open(base) as f:
            defaults = yaml.safe_load(f) or {}

    override: dict = {}
    if path is not None and path.exists():
        with open(path) as f:
            override = yaml.safe_load(f) or {}

    merged = _deep_merge(defaults, override)

    if "paths" not in merged:
        raise UserError("paths section required in configuration")

    return DubConfig.model_validate(merged)


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Deep-merge overlay into base, mutating base."""
    result = base.copy()
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result