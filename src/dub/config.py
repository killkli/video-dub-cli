"""config.py — YAML config loading + CLI override merging."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from dub.errors import ConfigError, UserError


class PathsConfig(BaseModel):
    qwenasr_cli: Path
    omnivoice_python: Path
    skills_dir: Path
    # Legacy only: historical Hermes subtitle-translation script path.
    # Standalone CLI translation now uses `translation.provider/model`.
    translation_skill: Path
    dub_root: Path = Field(default_factory=lambda: Path.home() / ".hermes")


class TranslationConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    api_env_var: str = "GOOGLE_API_KEY"
    temperature: float = 0.2
    mode: str = "delegate"
    translated_srt: Path | None = None


class DefaultsConfig(BaseModel):
    source_lang: str = "en"
    target_lang: str = "zh"
    vocal_gain: float = 3.0
    inst_gain: float = -3.0
    keep_fulltrack: bool = False


class RetryConfig(BaseModel):
    max_attempts: int = 3
    backoff_seconds: float = 5.0
    retry_on: list[str] = Field(
        default_factory=lambda: [
            "subprocess.CalledProcessError",
            "TimeoutError",
            "ConnectionError",
        ]
    )


class LoggingConfig(BaseModel):
    level: str = "INFO"
    json_logs: bool = False
    file: str | None = None
    progress: str = "rich"


class DubConfig(BaseModel):
    paths: PathsConfig = Field(default_factory=lambda: PathsConfig.model_validate(DEFAULT_PATHS))
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def merge_cli_overrides(
        self,
        *,
        source_lang: str | None = None,
        target_lang: str | None = None,
        vocal_gain: float | None = None,
        inst_gain: float | None = None,
        keep_fulltrack: bool | None = None,
        translate_mode: str | None = None,
        translated_srt: Path | None = None,
    ) -> "DubConfig":
        cfg = self.model_copy(deep=True)
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
        if translate_mode is not None:
            cfg.translation.mode = translate_mode
        if translated_srt is not None:
            cfg.translation.translated_srt = translated_srt
        return cfg


DEFAULT_PATHS = {
    "qwenasr_cli": "/path/to/qwenasr-mlx",
    "omnivoice_python": "/path/to/omnivoice-python",
    "skills_dir": "/path/to/video-dubbing-pipeline/scripts",
    "translation_skill": "/path/to/subtitle_translation.py",
    "dub_root": str(Path.home() / ".hermes"),
}


def _normalize_raw(raw: dict | None) -> dict:
    data = copy.deepcopy(raw or {})
    if "paths" not in data:
        raise UserError("paths section required")
    merged_paths = {**DEFAULT_PATHS, **(data.get("paths") or {})}
    data["paths"] = merged_paths
    return data


def load_config(path: Path | str | None = None) -> DubConfig:
    search = [Path(path)] if path else [Path("~/.config/dub/config.yaml").expanduser()]
    for p in search:
        if p.exists():
            try:
                raw = yaml.safe_load(p.read_text()) or {}
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in {p}: {e}") from e
            try:
                return DubConfig.model_validate(_normalize_raw(raw))
            except ValidationError as e:
                raise UserError(str(e)) from e

    return DubConfig(paths=PathsConfig.model_validate(DEFAULT_PATHS))


__all__ = [
    "DubConfig",
    "PathsConfig",
    "TranslationConfig",
    "DefaultsConfig",
    "RetryConfig",
    "LoggingConfig",
    "load_config",
    "UserError",
]
