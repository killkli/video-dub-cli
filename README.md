# video-dub-cli

> Resumable CLI pipeline for translating and dubbing videos into Chinese.

```bash
dub run talk.mp4 --source-lang en --target-lang zh
```

`video-dub-cli` packages a multi-stage video-dubbing workflow into a single CLI entrypoint with persistent project state, resumability, and explicit artifact contracts.

## Highlights

- **Single entrypoint**: run the full workflow with `dub run`
- **Resumable by design**: continue interrupted runs with `dub resume`
- **Artifact-driven workflow**: each stage persists outputs on disk
- **Operator-grade validation**: `status`, `clean`, and `validate` are built in
- **Real pipeline stages**: stems → ASR → ref-audio → translation → TTS → final assembly

## Pipeline

1. Vocal/instrumental separation
2. ASR transcription
3. Reference-audio extraction per segment
4. Subtitle translation
5. TTS dubbing per segment
6. Final MP4 assembly and mix

Because every stage writes durable artifacts, the pipeline can resume from partial completion instead of restarting from zero.

## Release status

Current version: **v0.1.0**

This release is usable as an **operator-grade CLI**:
- `dub run`, `dub resume`, `dub status`, `dub clean`, and `dub validate` are implemented
- stage state is stored in `.dub/state.json`
- English→Chinese and Japanese→Chinese workflows have operator QA coverage
- the repo is suitable for real runs, not just scaffold/demo usage

Current boundary:
- this is not yet a zero-intervention consumer product for arbitrary input videos
- users are still expected to understand config, artifacts, and translation mode choice

## Supported workflows

### Use an existing translated subtitle file

```bash
dub run talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### Let the CLI translate English to Chinese

```bash
dub run talk.mp4 --source-lang en --target-lang zh
```

### Let the CLI translate Japanese to Chinese

```bash
dub run talk.mp4 --source-lang ja --target-lang zh
```

### Resume an interrupted run

```bash
dub resume --project-dir /path/to/dub-project/
```

## Installation

Recommended: Python 3.11 in a virtual environment.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify installation:

```bash
dub --help
```

## Quick start

### 1. Prepare config

Start from a canonical example config:

```bash
cp examples/config_delegate_en2zh.yaml /path/to/config.yaml
```

Then replace all `/path/to/...` placeholders with the real paths for your own machine.

### 2. Run the pipeline

```bash
dub run /path/to/input/my_talk.mp4 --source-lang en --target-lang zh
```

### 3. Inspect the final output

Typical output location:

```text
/path/to/dub-project/07_final/video_dubbed_stem.mp4
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

### Clean

```bash
dub clean --project-dir <project-dir>
```

### Validate

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

A run creates a project directory like this:

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

- `QUICKSTART.md`
- `DESIGN.md`
- `docs/operator-qa-supported-flow-2026-06-02.md`
- `docs/operator-runbook.md`
- `docs/release-handoff-checklist.md`
- `docs/qa-matrix-en-ja-zh-2026-06-02.md`

## Testing

Run the main suite:

```bash
pytest
```

Run integration coverage when needed:

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
