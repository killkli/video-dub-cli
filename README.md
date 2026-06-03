# video-dub-cli

> Resumable CLI pipeline for translating and dubbing videos into Chinese.
> A single repo, a single install, no other clones required.

```bash
uv sync --extra all
uv run dub doctor                 # confirm prerequisites
uv run dub en2zh talk.mp4
```

`video-dub-cli` packages a multi-stage video-dubbing workflow into a
single CLI entrypoint with persistent project state, resumability, and
explicit artifact contracts.

## What is self-contained in this repo (and what is not)

| Concern | Self-contained? | Notes |
|---|---|---|
| CLI shell, config, validation, retry | yes | the `dub` script and friends ship in this repo |
| Pipeline scripts (stems, ref-audio, loudnorm, remix) | yes | vendored under `vendor/pipeline_scripts/` |
| Translation stage (Gemini REST) | yes | in-process logic in `src/dub/translator_gemini.py` |
| ASR default backend (`qwenasr-mlx`) | **partial** | discoverable on `$PATH`; install is operator's job (see [ASR install](#asr-install-qwenasr-mlx)) |
| TTS backends (OmniVoice, VoxCPM) | **partial** | adapter registry is in-repo; model stacks are operator-provided and `dub doctor` reports per-backend readiness |
| ffmpeg / ffprobe | **system dep** | install via your OS package manager before any real run |
| Translation API key (Gemini) | **operator-supplied** | export `GOOGLE_API_KEY` (or `GEMINI_API_KEY`); see [API key setup](#api-key-setup) |

This contract is verified end-to-end on `feature/standalone-repo-uv` by
`docs/qa-standalone-matrix.md` (T6). A fresh clone + `uv sync --extra
dev` + `uv run dub doctor` + a fake-backend end-to-end smoke all pass.

## Highlights

- **One-shot operator aliases**: `dub en2zh`, `dub ja2zh`
- **Advanced/base entrypoint**: `dub run`, plus `dub resume`, `dub status`, `dub clean`, `dub validate`, `dub doctor`, `dub bootstrap`
- **Resumable by design**: continue interrupted runs with `dub resume`
- **Artifact-driven workflow**: each stage persists outputs on disk under `01_raw_video/`, `02_stems/`, ... `07_final/`
- **Operator-grade validation**: `status`, `clean`, `validate`, and the readiness check `dub doctor` are first-class
- **Standalone install**: `uv sync --extra all` is the only install step; no other repos, no `~/.hermes/...` paths required
- **Real pipeline stages**: stems → ASR → ref-audio → translation → TTS → final assembly

## Pipeline

1. Vocal/instrumental separation
2. ASR transcription
3. Reference-audio extraction per segment
4. Subtitle translation
5. TTS dubbing per segment
6. Final MP4 assembly and mix

Because every stage writes durable artifacts, the pipeline can resume
from partial completion instead of restarting from zero.

## Supported workflows

### Use an existing translated subtitle file

```bash
uv run dub run talk.mp4 \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt talk.zhtw.srt
```

### One-shot English → Chinese operator flow

```bash
uv run dub en2zh talk.mp4
```

### One-shot Japanese → Chinese operator flow

```bash
uv run dub ja2zh talk.mp4
```

### Advanced/base entrypoint (same pipeline, explicit languages)

```bash
uv run dub run talk.mp4 --source-lang en --target-lang zh
```

### Resume an interrupted run

```bash
uv run dub resume --project-dir /path/to/dub-project/
```

## Installation (the standalone contract)

### 1. Clone the repo

```bash
git clone https://codeberg.org/killkli/video-dub-cli
cd video-dub-cli
```

### 2. Install the package with `uv`

The package is a normal `pyproject.toml` project. `uv` is the supported
install manager; it reads `uv.lock` and resolves a reproducible
environment.

```bash
# For full standalone stack (CLI + translation + TTS helpers + ASR helpers):
uv sync --extra all

# For dev / test work:
uv sync --extra dev

# Bare CLI only (unit tests use this):
uv sync
```

`uv` will create a local `.venv/` and install:

- the `dub` script
- the `dub-doctor` and `dub-bootstrap` script entrypoints
- all extras declared under `[project.optional-dependencies]`
  (`translation`, `tts`, `asr`, `pipeline`, `dev`, `all`)

Verify the install:

```bash
uv run dub --help
uv run dub doctor
```

> If you do not have `uv`, install it first:
> `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 3. Install system tools

`ffmpeg` and `ffprobe` are required for any real media run. `dub doctor`
will tell you if they are missing.

```bash
# macOS
brew install ffmpeg

# Debian / Ubuntu
sudo apt-get install -y ffmpeg
```

### 4. Set up the translation API key

`dub run` with `--translate-mode delegate` (the default) calls Gemini
for translation. The key is read from the environment; no key is
baked into the repo.

```bash
# Option A: export directly
export GOOGLE_API_KEY=your_google_api_key

# Option B: copy the example file and use a dotenv loader
cp .env.example .env
# edit .env, then `set -a; source .env; set +a` or use your loader
```

`dub doctor` checks `GOOGLE_API_KEY` first and falls back to
`GEMINI_API_KEY`; either works.

### 5. Install the ASR backend

`qwenasr-mlx` is the ASR CLI this pipeline calls. The repo does not
vendor it; it is discovered on `$PATH` (the default
`paths.qwenasr_cli` resolves to the bare name `qwenasr-mlx`).

See [ASR install](#asr-install-qwenasr-mlx) below for install options.

## Quick start

### 1. Confirm readiness

```bash
uv run dub doctor
```

A passing run reports every check as `OK` and per-backend readiness
(`READY` / `BLOCKED`). A missing prerequisite shows up as `MISSING` or
`BLOCKED` with the exact gate that failed.

If something is missing, run:

```bash
uv run dub bootstrap
```

…and read the 7-line guidance. It points at the exact system tool, env
var, repo-owned wrapper directory, or backend gate that needs attention.

### 2. Prepare config

Start from a canonical example config:

```bash
cp examples/config_delegate_en2zh.yaml /path/to/config.yaml
```

The example config ships with sensible defaults — most fields are
optional. In the standalone contract, operators normally only need to
override `paths.omnivoice_python` if OmniVoice lives in a different
Python environment. The repo-owned wrapper directory already defaults to
`vendor/pipeline_scripts` and should not need normal operator changes.
See [Configuration](#configuration) for the full breakdown.

### 3. Run the pipeline

```bash
uv run dub en2zh /path/to/input/my_talk.mp4
```

### 4. Inspect the final output

```text
/path/to/dub-project/07_final/video_dubbed_stem.mp4
```

## Configuration

The config schema lives in `src/dub/config.py`. The default config that
ships with the repo (no `--config` flag) is already valid for a fresh
operator. You only need a custom config to override:

- `paths.omnivoice_python` — if OmniVoice's Python lives outside the
  default interpreter path
- `paths.skills_dir` / `paths.tts_engines_dir` — only for advanced or
  legacy compatibility cases; normal operators should use the repo-owned
  default `vendor/pipeline_scripts`
- `defaults.vocal_gain` / `inst_gain` — to retune the mix
- `translation.model` — to pin a specific Gemini model

Full schema (canonical: see `src/dub/config.py`):

```yaml
paths:
  # Legacy compatibility only. Stage 2 is now repo-owned; operators do
  # not normally need to set this. Kept so older configs still parse.
  qwenasr_cli: null
  # Python interpreter that runs OmniVoice wrappers. Default: python3
  # from the dub venv. Override only if OmniVoice lives in a separate venv.
  omnivoice_python: python3
  # Vendored pipeline scripts. Default: <repo>/vendor/pipeline_scripts.
  # Override only if you have custom stems / ref-audio / remix scripts.
  skills_dir: <repo>/vendor/pipeline_scripts
  # Legacy compatibility only. The standalone CLI translates in-process
  # via translation.provider/model; this field is no longer read by any
  # active stage. Kept on the schema for one release.
  translation_skill: <repo>/src/dub/translator_gemini.py
  # Where new project directories are created. Default:
  # ~/video-dub-cli-runs/
  dub_root: ~/video-dub-cli-runs/
  # Advanced / legacy override only. Normal operators should leave the
  # repo-owned default alone.
  tts_engines_dir: <repo>/vendor/pipeline_scripts

translation:
  provider: gemini           # only "gemini" and "mock" are supported
  model: gemini-2.5-flash
  api_env_var: GOOGLE_API_KEY
  temperature: 0.2
  mode: delegate             # delegate | use-existing | skip

defaults:
  source_lang: en
  target_lang: zh
  vocal_gain: 3.0
  inst_gain: -3.0
  keep_fulltrack: false

retry:
  max_attempts: 3
  backoff_seconds: 5
  retry_on:
    - subprocess.CalledProcessError
    - TimeoutError
    - ConnectionError

logging:
  level: INFO
  json_logs: false
  progress: rich
```

Most fields have safe defaults — see the [Configuration cheatsheet](#configuration-cheatsheet) for the short version.

### Configuration cheatsheet

| I want to… | Override this field |
|---|---|
| Change the Gemini model | `translation.model` |
| Use a different API key env var | `translation.api_env_var` (e.g. `GEMINI_API_KEY`) |
| Tune the dub/vocal mix | `defaults.vocal_gain`, `defaults.inst_gain` |
| Keep the full original track in the final mix | `defaults.keep_fulltrack: true` |
| Use a private TTS wrapper script directory | `paths.tts_engines_dir` |
| Use a separately-installed OmniVoice Python | `paths.omnivoice_python: /path/to/python3` |
| Change where new project directories are created | `paths.dub_root` |
| Use a different ASR CLI binary | `paths.qwenasr_cli: my-asr-cli` |

## ASR install (`qwenasr-mlx`)

`qwenasr-mlx` is the only known non-PyPI runtime dependency. The repo
discovers it on `$PATH` (default `paths.qwenasr_cli = "qwenasr-mlx"`)
and `dub doctor` reports whether it is reachable.

Install options (pick one):

```bash
# Option A: pipx (recommended; isolated environment)
pipx install qwenasr-mlx

# Option B: pip into the dub venv
uv pip install qwenasr-mlx

# Option C: pipx from git, if not on PyPI yet
pipx install git+https://github.com/<qwenasr-mlx-repo>
```

Then verify:

```bash
which qwenasr-mlx
uv run dub doctor    # should show qwenasr_cli: OK
```

If you have it under a non-default name or path, override:

```bash
uv run dub run talk.mp4 --source-lang en --target-lang zh \
  --config /path/to/config.yaml
# ...with config.yaml containing:
#   paths:
#     qwenasr_cli: /full/path/to/your-asr
```

## Core commands

| Command | Purpose |
|---|---|
| `dub en2zh VIDEO [OPTIONS]` | Run the common English → Chinese one-shot operator flow |
| `dub ja2zh VIDEO [OPTIONS]` | Run the common Japanese → Chinese one-shot operator flow |
| `dub run VIDEO --source-lang <lang> --target-lang zh [OPTIONS]` | Advanced/base entrypoint for explicit language control |
| `dub resume --project-dir <project-dir>` | Continue a previous (interrupted or partially failed) run |
| `dub status --project-dir <project-dir>` | Print per-stage status |
| `dub clean --project-dir <project-dir> [--stage N]` | Remove stage outputs (preserve source by default) |
| `dub validate --project-dir <project-dir>` | Verify final MP4 contract |
| `dub doctor [--config CONFIG]` | Readiness check (prerequisites, per-backend readiness) |
| `dub bootstrap` | Print 6-line bootstrap guidance |

Common `dub run` options:

- `--project-dir`
- `--config`
- `--translate-mode delegate|skip|use-existing`
- `--translated-srt`
- `--vocal_gain` / `--inst_gain`
- `--keep_fulltrack`
- `--yes`

## Translation modes

### `delegate` (default)
Use the built-in translation stage. Reads the API key from the env
(`GOOGLE_API_KEY` / `GEMINI_API_KEY`), calls Gemini, writes the
translated SRT.

Good for: fresh projects, normal CLI-driven translation flow.

### `use-existing`
Use a pre-existing translated subtitle file. Requires
`--translated-srt /path/to/file.srt`.

Good for: reviewed translations, external subtitle workflows,
deterministic reruns.

### `skip`
Skip the translation stage and reuse the translated subtitle already
stored inside the project. Requires a prior `delegate` or
`use-existing` run; the canonical path
`<project>/05_translated_srt/video.zhtw.srt` must already exist.

## Project layout

A run creates a project directory like:

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
See `docs/operator-runbook.md` for the failure-recovery procedures that
read this state.

## API key setup

The `delegate` translation mode calls Gemini. The key is read from the
environment at run time — never from a hard-coded file in the repo.

| Env var | Honored? | Notes |
|---|---|---|
| `GOOGLE_API_KEY` | yes (primary) | Set this if you only need one |
| `GEMINI_API_KEY` | yes (fallback) | Used only if `GOOGLE_API_KEY` is unset |

Set it in your shell, your dotfiles, or your CI environment. `dub
doctor` reports which env var (if any) it found.

For a local `.env` style workflow, copy `.env.example` to `.env` and
source it in your shell before invoking `dub run`:

```bash
cp .env.example .env
# edit .env to put your real key
set -a; source .env; set +a
uv run dub en2zh talk.mp4
```

## Documentation

- `QUICKSTART.md` — 5-minute happy-path walkthrough
- `DESIGN.md` — design notes
- `docs/standalone-dependency-map.md` — what is and is not self-contained (T1)
- `docs/qa-standalone-matrix.md` — fresh-operator install / usage matrix (T6)
- `docs/operator-runbook.md` — failure recovery guide
- `docs/tts-backend-consolidation.md` — TTS adapter contract (T5)
- `docs/release-handoff-checklist.md`
- `docs/qa-matrix-en-ja-zh-2026-06-02.md`

## Testing

Run the main suite:

```bash
uv run pytest
```

Run only the unit / CLI / contract tests (skips integration):

```bash
uv run pytest tests/ -q --ignore=tests/integration
```

Run the integration suite (requires real ASR / TTS / ffmpeg and an
API key):

```bash
uv run pytest tests/integration -m integration
```

## Known limits and open risks

The standalone contract is structurally achieved (verified by T6), but
some pieces are still operator-graded:

- **Demucs model download on first run** (R2 in the dep map). `dub
  bootstrap` does not prefetch the model. The first real run will
  download it.
- **TTS in-process import** (R1). Stage 5 still shells out to
  `dubbing_batch_tts*.py` wrappers. The adapter registry is in-repo
  (`src/dub/tts_engines/`), and `dub doctor` reports per-backend
  readiness, but moving the actual call in-process is a follow-up.
- **qwenasr-mlx PyPI story** (R5). The only non-PyPI runtime
  dependency is `qwenasr-mlx`. Until it ships on PyPI, install via
  `pipx` from git (see [ASR install](#asr-install-qwenasr-mlx)).

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

Package metadata:
- package: `video-dub-cli`
- CLI entrypoints: `dub`, `dub-doctor`, `dub-bootstrap`
- version: `0.1.0`

## License

MIT
