# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-02

### Added

- **T0 – repo init**: Initial project scaffolding, `pyproject.toml`, `DESIGN.md` as single source of truth
- **T1 – CLI skeleton**: `dub` CLI with `--help`, `--version`, `run/resume/status/clean/validate` subcommands via Click
- **T2 – CLI subcommands**: Full argument parsing for `run`, `resume`, `status`, `clean`, `validate` with all options per DESIGN.md §2
- **T3 – config + state**: YAML config loader with merge priority, `.dub/state.json` schema with per-stage status tracking
- **T4 – stages integration**: 6 stage scripts wired into `runner.py`; skip-existing logic for all 6 stages; ASR routing (en→QwenasrMLX, ja→QwenasrMLX)
- **T5 – resume/status/clean**: `dub resume` reading `state.json`, `dub status` with table output, `dub clean` with `--keep-source` and `--stage`
- **T6 – QA 3 scenarios**: Smoke test (30s MP4, full pipeline), resume test (kill at stage 5, resume, byte-compare), idempotency test (delete line_5_ref.wav, partial TTS retry)
- **T7 – docs + skill assessment**: Comprehensive README (12 sections), QUICKSTART.md (5-min onboarding), 3 example configs (en2zh/ja2zh/use-existing), skill-assessment report, CHANGELOG.md

### Features

| Feature | Description |
|---------|-------------|
| `dub run` | Single-command video dubbing with skip-existing |
| `dub resume` | Resume from last successful stage |
| `dub status` | Stage-by-stage progress table |
| `dub clean` | Clean partial artifacts, keep source |
| `dub validate` | Validate project structure and outputs |
| Config override | CLI flags > YAML > ~/.config/dub/config.yaml > defaults |
| Per-stage retry | 3 attempts with exponential backoff |
| Rich progress | Real-time stage bars and sub-progress |

### Configuration

Example configs added:
- `examples/config_en2zh.yaml` — English → Chinese (OmniVoice TTS)
- `examples/config_ja2zh.yaml` — Japanese → Chinese (VoxCPM TTS)
- `examples/config_with_translated_srt.yaml` — Skip translation stage with pre-translated SRT

### Documentation

- `README.md` — 12 sections: features, install, quickstart, full commands, architecture, config schema, stage pipeline, resume/status/clean, testing, troubleshooting, license
- `QUICKSTART.md` — 5-minute onboarding from clone to first run
- `docs/skill-assessment.md` — Assessment of packaging CLI as Hermes Agent skill; recommends new `video-dub-cli` skill (defer until T6 smoke test passes)
- `CHANGELOG.md` — This file

### Known Limitations

- GPU OOM: TTS stage most at-risk; no graceful degradation (fails directly)
- Concurrent projects: No cross-project locking; two CLI runs on same `project-dir` will race
- YouTube: Not supported in v0.1.0 (use `yt-dlp` to download first)
- zh→en: Interface reserved, not tested in v0.1.0

### Dependencies

- `click` 8.x
- `rich` 13.x
- `pyyaml` 6.x
- `tenacity` 8.x
- `loguru` 0.7.x
- Python 3.11+