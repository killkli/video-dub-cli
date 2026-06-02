"""config.py — YAML config loading + CLI override merging."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from dub.errors import ConfigError


# ── schema ────────────────────────────────────────────────────────────────────

class Paths:
    qwenasr_cli: Path = Path("/path/to/qwenasr-mlx")
    omnivoice_python: Path = Path("/path/to/omnivoice-python")
    skills_dir: Path = Path("/path/to/video-dubbing-pipeline/scripts")
    dub_root: Path = Path("~/.hermes").expanduser()
    translation_skill: Path = Path("/path/to/subtitle_translation.py")

    def __init__(self, d: dict[str, Any] | None = None) -> None:
        if d:
            self.qwenasr_cli = Path(d.get("qwenasr_cli", self.qwenasr_cli))
            self.omnivoice_python = Path(d.get("omnivoice_python", self.omnivoice_python))
            self.skills_dir = Path(d.get("skills_dir", self.skills_dir))
            self.dub_root = Path(d.get("dub_root", self.dub_root)).expanduser()
            self.translation_skill = Path(d.get("translation_skill", self.translation_skill))


class Defaults:
    source_lang: str = "en"
    target_lang: str = "zh"
    vocal_gain: float = 3.0
    inst_gain: float = -3.0
    keep_fulltrack: bool = False

    def __init__(self, d: dict[str, Any] | None = None) -> None:
        if d:
            self.source_lang = d.get("source_lang", self.source_lang)
            self.target_lang = d.get("target_lang", self.target_lang)
            self.vocal_gain = float(d.get("vocal_gain", self.vocal_gain))
            self.inst_gain = float(d.get("inst_gain", self.inst_gain))
            self.keep_fulltrack = bool(d.get("keep_fulltrack", self.keep_fulltrack))


class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 5.0
    retry_on: list[str] = ["subprocess.CalledProcessError", "TimeoutError", "ConnectionError"]

    def __init__(self, d: dict[str, Any] | None = None) -> None:
        if d:
            self.max_attempts = int(d.get("max_attempts", self.max_attempts))
            self.backoff_seconds = float(d.get("backoff_seconds", self.backoff_seconds))
            self.retry_on = list(d.get("retry_on", self.retry_on))


class LoggingConfig:
    level: str = "INFO"
    json_logs: bool = False
    file: str = "<project>/.dub/log.txt"
    progress: str = "rich"

    def __init__(self, d: dict[str, Any] | None = None) -> None:
        if d:
            self.level = d.get("level", self.level)
            self.json_logs = bool(d.get("json_logs", self.json_logs))
            self.file = str(d.get("file", self.file))
            self.progress = d.get("progress", self.progress)


class DubConfig:
    paths: Paths = Paths()
    defaults: Defaults = Defaults()
    retry: RetryConfig = RetryConfig()
    logging: LoggingConfig = LoggingConfig()

    def __init__(self, d: dict[str, Any] | None = None) -> None:
        if d:
            self.paths = Paths(d.get("paths"))
            self.defaults = Defaults(d.get("defaults"))
            self.retry = RetryConfig(d.get("retry"))
            self.logging = LoggingConfig(d.get("logging"))

    def merge_cli_overrides(
        self,
        *,
        source_lang: str | None = None,
        target_lang: str | None = None,
        vocal_gain: float | None = None,
        inst_gain: float | None = None,
        keep_fulltrack: bool | None = None,
    ) -> "DubConfig":
        """Return a new config with CLI flags overlaid."""
        cfg = copy.deepcopy(self)
        if source_lang is not None:
            cfg.defaults.source_lang = source_lang
        if target_lang is not None:
            cfg.defaults.target_lang = target_lang
        if vocal_gain is not None:
            cfg.defaults.vocal_gain = vocal_gain
        if inst_gain is not None:
            cfg.defaults.inst_gain = inst_gain
        if keep_fulltrack is not None:
            cfg.defaults.keep_fulltrack = keep_fulltrack
        return cfg


# ── loader ────────────────────────────────────────────────────────────────────

def load_config(path: Path | str | None = None) -> DubConfig:
    """
    Load config from path (default ~/.config/dub/config.yaml).
    Return default DubConfig if file is absent.
    """
    default_locations = [Path("~/.config/dub/config.yaml").expanduser()]
    search = []
    if path:
        search = [Path(path)]
    search += default_locations

    for p in search:
        if p.exists():
            try:
                with open(p) as f:
                    raw = yaml.safe_load(f) or {}
                return DubConfig(raw)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {p}: {e}") from e

    return DubConfig()


__all__ = ["DubConfig", "load_config"]