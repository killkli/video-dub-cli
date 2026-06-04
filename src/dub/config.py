"""config.py — YAML config loading + CLI override merging."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from dub.errors import ConfigError, UserError


class PathsConfig(BaseModel):
    # Legacy only: qwenasr_cli used to point at an external CLI binary. The
    # stage is now repo-owned (see src/qwenasr_mlx_cli); this field is kept
    # as an optional, unused knob for backward-compatibility with old YAML
    # configs. Operators no longer need to set it.
    qwenasr_cli: Path | None = None
    omnivoice_python: Path = Path("python3")
    skills_dir: Path = Path(__file__).resolve().parents[2] / "vendor" / "pipeline_scripts"
    # Legacy only: historical Hermes subtitle-translation script path.
    # Standalone CLI translation now uses `translation.provider/model`.
    translation_skill: Path = Path(__file__).resolve().parents[2] / "src" / "dub" / "translator_gemini.py"
    dub_root: Path = Field(default_factory=lambda: Path.home() / "video-dub-cli-runs")
    # Repo-owned runtime directory. Operators should not need to set this;
    # it defaults to vendor/pipeline_scripts inside this repo.
    tts_engines_dir: Path = Path(__file__).resolve().parents[2] / "vendor" / "pipeline_scripts"
    # Test-only escape hatches for the ASR stage. Both default to None and
    # are no-ops in production. They exist so the integration suite can run
    # end-to-end without real MLX model weights — see
    # src/dub/stages/asr.py for the contract and docs/standalone-operator.md
    # for the operator-facing documentation.
    asr_test_fixture_srt: Path | None = None
    asr_test_backend_fail: bool = False


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
    # TTS assembler routing. Default is the legacy single-filter_complex
    # path (dubbing_assemble_loudnorm.py); flip use_batched_assembler=True
    # to switch to the batched variant (assemble_tts_batched.py) which
    # keeps each filter_complex under the FFmpeg command-line length
    # limit and is the supported path for 60+ clip videos. See
    # vendor/pipeline_scripts/assemble_tts_batched.py for the batching
    # contract.
    use_batched_assembler: bool = False
    tts_batch_size: int = 30


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
    "omnivoice_python": "python3",
    "skills_dir": str(Path(__file__).resolve().parents[2] / "vendor" / "pipeline_scripts"),
    "translation_skill": str(Path(__file__).resolve().parents[2] / "src" / "dub" / "translator_gemini.py"),
    "dub_root": str(Path.home() / "video-dub-cli-runs"),
}


def _normalize_raw(raw: dict | None) -> dict:
    data = copy.deepcopy(raw or {})
    merged_paths = {**DEFAULT_PATHS, **(data.get("paths") or {})}
    data["paths"] = merged_paths
    return data


def load_config(path: Path | str | None = None) -> DubConfig:
    search = [Path(path)] if path else [Path("/path/to/config.yaml").expanduser()]
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
