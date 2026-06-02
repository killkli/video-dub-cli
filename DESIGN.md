# video-dub-cli Design Specification

> Placeholder — T0 pending. Full spec to be added by T0.

## 1. Overview

`video-dub-cli` is a command-line tool for translating and dubbing video files using a staged pipeline.

## 2. CLI Interface

```
dub --config CONFIG [--verbose] [--dry-run]
```

## 3. Config Schema

(See T3 for full schema definition)

## 4. Pipeline Stages

1. **stems** — Separate audio stems from video
2. **asr** — Automatic speech recognition
3. **ref_audio** — Record reference audio for TTS voice cloning
4. **translate** — Translate transcripts
5. **tts** — Generate TTS audio from translated transcripts
6. **assemble** — Assemble final dubbed video

## 5. Architecture

- `src/dub/` — main package
- `src/dub/stages/` — one module per pipeline stage
- `src/dub/config.py` — config loading and validation
- `src/dub/state.py` — project state tracking
- `src/dub/runner.py` — stage orchestration

## 6. Error Handling

- `DubError` — base exception
- `UserError` — invalid user input
- `StageError` — stage execution failure
- `TranslationError` — translation failures

## 7. Logging

Use `loguru` with structured output.

## 8. Retry Logic

Use `tenacity` for retry with exponential backoff.

## 9. Project Structure

```
src/dub/
  __init__.py
  __main__.py
  cli.py
  config.py
  state.py
  project.py
  runner.py
  retry.py
  progress.py
  logging.py
  errors.py
  stages/
    __init__.py
    base.py
    stems.py
    asr.py
    ref_audio.py
    translate.py
    tts.py
    assemble.py
tests/
  __init__.py
  test_smoke.py
  test_config.py
  test_state.py
examples/
  config_en2zh.yaml
  config_ja2zh.yaml
  config_with_translated_srt.yaml
```
