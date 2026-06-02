# video-dub-cli

A resumable CLI workflow for translating and dubbing videos into Chinese.

```bash
dub run talk.mp4 --source-lang en --target-lang zh
```

`video-dub-cli` turns a multi-stage dubbing pipeline into a single operator-facing command with persistent project state, resumability, and explicit artifact contracts.

## What it does

Pipeline stages:

1. Vocal/instrumental separation
2. ASR transcription
3. Reference-audio extraction per segment
4. Subtitle translation
5. TTS dubbing per segment
6. Final MP4 assembly and mix

The CLI stores artifacts on disk for every stage, so interrupted runs can continue with `dub resume` instead of restarting from scratch.

## Current status

This repo is at **v0.1.0** and is usable as an **operator-grade CLI**.

That means:
- `dub run`, `dub resume`, `dub status`, `dub clean`, and `dub validate` are implemented
- stage state is persisted to disk
- the supported English→Chinese and Japanese→Chinese workflows have operator QA coverage
- the tool is designed for real runs, not just a demo skeleton

It does **not** mean every arbitrary video will succeed with zero operator judgment. The current release expects the user to understand config, project artifacts, and translation mode selection.

## Supported workflows

### 1. Use an existing translated subtitle file
Best when you already have a reviewed Chinese SRT.

```bash
dub run talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### 2. Let the CLI translate from English to Chinese

```bash
dub run talk.mp4 --source-lang en --target-lang zh
```

### 3. Let the CLI translate from Japanese to Chinese

```bash
dub run talk.mp4 --source-lang ja --target-lang zh
```

### 4. Resume an interrupted project

```bash
dub resume --project-dir ~/.hermes/dub-talk-YYYYMMDD-HHMMSS/
```

## Installation

Recommended: Python 3.11 in a virtual environment.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify:

```bash
dub --help
```

## Quick start

### Step 1: prepare config

Start from one of the example configs:

```bash
cp examples/config_delegate_en2zh.yaml ~/.config/dub/config.yaml
```

Then edit the paths and tool settings to match your machine.

### Step 2: run the pipeline

```bash
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

### Step 3: inspect output

Typical final output:

```text
~/.hermes/dub-my_talk-YYYYMMDD-HHMMSS/07_final/video_dubbed_stem.mp4
```

## Core commands

### Run

```bash
dub run VIDEO --source-lang en --target-lang zh [OPTIONS]
```

Common options:
- `--project-dir`
- `--config`
- `--translate-mode delegate|skip|use-existing`
- `--translated-srt`
- `--vocal-gain`
- `--inst-gain`
- `--keep-fulltrack`
- `--yes`

### Resume

```bash
dub resume --project-dir <project-dir>
```

### Status

```bash
dub status --project-dir <project-dir>
```

### Clean partial artifacts

```bash
dub clean --project-dir <project-dir>
```

### Validate project structure

```bash
dub validate --project-dir <project-dir>
```

## Translation modes

### `delegate`
Use the built-in translation stage.

Good for:
- fresh projects
- normal CLI-driven translation flow

### `use-existing`
Use a pre-existing translated subtitle file.

Requires:
- `--translated-srt /path/to/file.srt`

Good for:
- reviewed translations
- external subtitle workflows
- deterministic reruns

### `skip`
Skip the translation stage and reuse the translated subtitle already stored inside the project.

Requires:
- an existing project
- the translated SRT artifact already present in the project tree

## Project layout

A run creates a project directory with stage artifacts and state:

```text
dub-<topic>-<timestamp>/
├── 01_raw_video/
├── 02_stems/
├── 03_asr/
├── 04_ref_audio/
├── 05_translated_srt/
├── 06_tts_wav/
├── 07_final/
└── .dub/state.json
```

This layout is the basis for resumability, validation, and recovery.

## Documentation

Operator and handoff docs live in `docs/`:

- `docs/operator-qa-supported-flow-2026-06-02.md`
- `docs/operator-runbook.md`
- `docs/release-handoff-checklist.md`
- `docs/qa-matrix-en-ja-zh-2026-06-02.md`
- `QUICKSTART.md`
- `DESIGN.md`

## Testing

Run the test suite:

```bash
pytest
```

Run targeted integration coverage when needed:

```bash
pytest tests/integration -m integration
```

## External toolchain expectations

This CLI orchestrates external components. Depending on your config and workflow, you may need:

- ASR tooling
- subtitle translation route/config
- TTS tooling
- ffmpeg / ffprobe
- model/runtime dependencies referenced by your YAML config

The repo includes the CLI and workflow logic; environment-specific provider/tool wiring is configured outside the package.

## Limitations

Current release boundaries:

- not every input video is guaranteed to work unattended
- translation and TTS quality still depend on external provider/tool configuration
- some flows are operator-oriented rather than consumer-app UX
- project recovery assumes the artifact contract is preserved

## Development

```bash
pip install -e ".[dev]"
pytest
```

Package metadata:
- package: `video-dub-cli`
- CLI entrypoint: `dub`
- version: `0.1.0`

## License

MIT
