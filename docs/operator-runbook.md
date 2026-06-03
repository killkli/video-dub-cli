# Operator Runbook — Failure Recovery Guide

**Date:** 2026-06-03
**Scope:** Recovery procedures for the `video-dub-cli` pipeline on
the standalone clone+uv contract.
**Reference QA matrices:**
- `docs/qa-matrix-en-ja-zh-2026-06-02.md` (en/ja route coverage)
- `docs/qa-standalone-matrix.md` (standalone install / usage matrix)

This runbook assumes the standalone install path (`uv sync` from a fresh
clone). If you are on a legacy venv install, the commands work the same
way — just drop the `uv run` prefix.

---

## Pre-flight: `dub doctor` and `dub bootstrap`

Before debugging a specific failure, confirm the standalone contract
holds on this host.

```bash
uv run dub doctor
```

A passing run reports each prerequisite as `OK` and per-backend TTS
readiness as `READY`. A failing run prints `MISSING` / `BLOCKED` lines
naming the exact gate that failed.

If anything is missing or blocked, the 6-line guidance is:

```bash
uv run dub bootstrap
```

That text points at the exact system tool, env var, or TTS backend that
needs attention. Fix the named gate, then re-run `dub doctor`.

---

## Reading Pipeline State

### `.dub/state.json`

Each project has a `.dub/state.json` at the project root. Key fields:

```json
{
  "input": {
    "source_lang": "en",
    "target_lang": "zh",
    "translate_mode": "delegate",
    "project_dir": "/path/to/project"
  },
  "stages": {
    "01_stems":    { "status": "done",    "attempts": 1 },
    "02_asr":      { "status": "done",    "attempts": 1 },
    "03_ref_audio":{ "status": "done",    "attempts": 1 },
    "04_translate":{ "status": "done",    "attempts": 1 },
    "05_tts":      { "status": "failed",  "attempts": 1, "error": "OOM" },
    "06_assemble": { "status": "pending", "attempts": 0 }
  }
}
```

**Stage status values:** `pending` | `running` | `done` | `failed` | `skipped`

To read the current state:

```bash
cat .dub/state.json | python3 -m json.tool
```

### `.dub/<stage>.log`

Each stage writes a log file to `.dub/` when it runs:

```
.dub/01_stems.log
.dub/02_asr.log
.dub/03_ref_audio.log
.dub/04_translate.log
.dub/05_tts.log
.dub/06_assemble_step1_tts.log
.dub/06_assemble_remix.log
```

To see the last 30 lines of any stage log:

```bash
tail -30 .dub/05_tts.log
```

To see errors only:

```bash
grep -i error .dub/05_tts.log
```

---

## Choosing `resume` vs `clean --stage N`

| Situation | Command |
|-----------|---------|
| Pipeline stopped mid-run (stage status = `running`) | `uv run dub resume` |
| A specific stage failed but earlier stages are fine | `uv run dub clean --project-dir <path> --stage <N>` then `uv run dub resume` |
| Want to re-run from scratch without touching source | `uv run dub clean --project-dir <path>` then re-run `uv run dub run` |

**Rule of thumb:**
- If the pipeline was killed or crashed mid-stage → `resume`
- If a stage completed but produced corrupt/bad output → `clean --stage N` + `resume`
- If you want to re-run everything downstream of a specific stage → `clean --stage N` + `resume`
- Never `clean` the source video (`01_raw_video/`) unless you want to delete the source

---

## Four Most Common Failure Modes

### FR-1: `use-existing` without `--translated-srt`

**Exact error:**
```
translate-mode=use-existing requires --translated-srt
```

**Cause:** Used `--translate-mode use-existing` but did not provide `--translated-srt <path>`.

**Recovery:**
```bash
uv run dub run <video> \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/your/translated.srt
```

---

### FR-2: `use-existing` with non-existent `--translated-srt` path

**Exact error:**
```
translated SRT not found: /nonexistent/path.srt
```

**Cause:** The file at `--translated-srt` does not exist.

**Recovery:**
```bash
# Verify the path exists:
ls -la /path/to/your/translated.srt

# Re-run with correct path:
uv run dub run <video> \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /correct/path/to/translated.srt
```

---

### FR-3: `skip` on fresh project (no prior translated SRT)

**Exact error:**
```
translate-mode=skip requires an existing translated subtitle at <project_dir>/05_translated_srt/video.zhtw.srt
```

**Cause:** Used `--translate-mode skip` on a project that has never run the translate stage. There is no `05_translated_srt/video.zhtw.srt` yet.

**Recovery:** Choose the correct mode for your situation:

```bash
# Option A: use use-existing if you have an external translation
uv run dub run <video> \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/translated.srt

# Option B: let CLI translate (delegate mode, default)
uv run dub run <video> --source-lang en --target-lang zh
```

---

### FR-4: Stage 5 (TTS) OOM or subprocess crash

**Symptoms:** Stage 5 halts with `status: failed`, `error: OOM` or similar in `.dub/05_tts.log`.

**Recovery:**
```bash
# Step 1: check current state
uv run dub status --project-dir <path>

# Step 2: resume — re-enters at the failed stage
uv run dub resume --project-dir <path>
```

The TTS stage has built-in per-line recovery: if some `line_<i>_tts.wav` files are missing or undersized after a failure, the stage will re-invoke TTS scoped to each missing cue via `--start N --end N`.

---

### FR-5: Stage 6 (assemble) ffprobe failure

**Symptoms:** Stage 6 halts with `status: failed`. ffprobe cannot read the output MP4, or the subprocess exited non-zero.

**Recovery:**
```bash
# Step 1: check state
uv run dub status --project-dir <path>

# Step 2: clean only stage 6 artifacts (keeps earlier stages intact)
uv run dub clean --project-dir <path> --stage 6

# Step 3: resume
uv run dub resume --project-dir <path>
```

`--stage 6` only removes artifacts from `07_final/`. Your earlier stages (`01_stems` through `06_tts_wav`) are preserved.

---

## New failure modes added by the standalone contract

### FR-6: `dub doctor` reports `qwenasr_cli: MISSING`

**Symptom:**
```
qwenasr_cli: MISSING (missing)
```

**Cause:** `qwenasr-mlx` is not on `$PATH`. The standalone contract
delegates ASR install to the operator (it is the only known non-PyPI
runtime dependency).

**Recovery:**
```bash
# Pick one (see QUICKSTART.md for the full list):

# A. pipx (recommended; isolated environment)
pipx install qwenasr-mlx

# B. pip into the dub venv
uv pip install qwenasr-mlx

# C. pipx from git, if not on PyPI yet
pipx install git+https://github.com/<qwenasr-mlx-repo>
```

Then verify:
```bash
which qwenasr-mlx
uv run dub doctor    # should show qwenasr_cli: OK
```

If `qwenasr-mlx` is installed under a different name or path, override
`paths.qwenasr_cli` in your config (see README's configuration
cheatsheet).

---

### FR-7: `dub doctor` reports `gemini_api_key: MISSING`

**Symptom:**
```
gemini_api_key: MISSING (GOOGLE_API_KEY,GEMINI_API_KEY)
```

**Cause:** No Gemini API key is in the environment. `--translate-mode
delegate` (the default) requires one.

**Recovery:**
```bash
# Option A: direct export
export GOOGLE_API_KEY=*** # Option B: .env style
cp .env.example .env
# edit .env to put your real key
set -a; source .env; set +a
uv run dub doctor    # should show gemini_api_key: OK (GOOGLE_API_KEY)
```

If you do not want to set a Gemini key, switch to
`--translate-mode use-existing` with a pre-translated SRT (FR-1 / FR-2).

---

### FR-8: `dub doctor` reports a TTS backend as `BLOCKED`

**Symptom:**
```
tts_backends:
  omnivoice: BLOCKED (missing: deps:torch)
  voxcpme:   BLOCKED (missing: deps:gradio_client, deps:opencc)
```

**Cause:** A TTS backend's dependencies are not satisfied in the active
Python interpreter.

**Recovery:** Each gate (wrapper / interpreter / deps / service) is
listed individually. The fix depends on which gate failed:

- `missing: deps:torch` → install `torch` (and `omnivoice`) in the
  Python at `paths.omnivoice_python` (default: the dub venv's
  `python3`).
- `missing: deps:gradio_client` / `deps:opencc` → `uv pip install
  gradio_client opencc-python-reimplemented` in the dub venv.
- `missing: service` → the named backend's local server is not
  running. For VoxCPM, start a local server on 127.0.0.1:8808 first.

You can also run the pipeline without a specific TTS backend by
choosing a different one in your config (see
`docs/tts-backend-consolidation.md`).

---

## Known Fragility (from T3 research)

These coupling weaknesses are known and not yet hardened:

### Weakness 1 — `source_lang` is dual-role but not locked per project

`source_lang` simultaneously controls ASR language and TTS script route. If you resume a project with a different config (or a future version adds a new language route), the pipeline may re-enter with a different ASR language or TTS script, causing inconsistency with already-existing artifacts.

**Operational mitigation:** Always use the same `--source-lang` when resuming a project. Do not mix `--source-lang en` first-run with `--source-lang ja` resume.

### Weakness 2 — `TranslationConfig.provider` is a weak contract

The config field `provider: gemini` looks like a configurable route,
but the stage code does not dispatch on it — it always calls
`translate_srt_file` (Gemini) unless `provider == "mock"`. Switching
to another backend via config will not work as expected.

**Operational mitigation:** Do not change `translation.provider` in config — only `gemini` and `mock` are supported.

### Weakness 3 — Dual translated SRT paths

Canonical path: `05_translated_srt/video.zhtw.srt`
Legacy compat copy: `05_translate/video.zhtw.srt`

Both are written by the translate stage. `validate` and `skip` only check the canonical path. The compat copy exists for legacy tool compatibility and may be removed in future versions without notice.

**Operational mitigation:** Treat `05_translated_srt/video.zhtw.srt` as the only stable contract. Do not reference `05_translate/video.zhtw.srt` in external tooling.

---

## Open risks from the standalone consolidation (T1 / T5 / T6)

These are tracked in `docs/standalone-dependency-map.md` and
`docs/qa-standalone-matrix.md`. They do not block standalone usage
today, but operators should be aware:

- **R1 — TTS in-process import.** Stage 5 still shells out to
  `dubbing_batch_tts*.py` wrappers. The adapter registry is in-repo
  (`src/dub/tts_engines/`) and `dub doctor` reports per-backend
  readiness, but the next consolidation pass is moving the actual call
  in-process.
- **R2 — Demucs model download on first run.** `dub bootstrap` does
  not prefetch the Demucs model. The first real run will download it.
- **R5 — qwenasr-mlx PyPI story.** Until `qwenasr-mlx` ships on PyPI,
  install via `pipx` from git (see FR-6).

---

## Quick Reference: CLI Commands

```bash
# Run pipeline
uv run dub run <video> --source-lang en --target-lang zh

# Check status
uv run dub status --project-dir <path>

# Validate outputs
uv run dub validate --project-dir <path>

# Resume after failure
uv run dub resume --project-dir <path>

# Clean stage N then resume
uv run dub clean --project-dir <path> --stage N
uv run dub resume --project-dir <path>

# Full clean (keeps source video)
uv run dub clean --project-dir <path>

# Read state
cat .dub/state.json | python3 -m json.tool

# Tail a stage log
tail -30 .dub/05_tts.log

# Pre-flight readiness check
uv run dub doctor

# 6-line bootstrap guidance
uv run dub bootstrap
```

> On a legacy venv install (not the standalone uv contract), drop the
> `uv run` prefix — the commands are otherwise identical.

---

## Full QA Matrices

For the complete test matrix see:
- `docs/qa-matrix-en-ja-zh-2026-06-02.md` — en/ja route scenarios (Rows 1–5) and failure-recovery scenarios (FR-1 through FR-5)
- `docs/qa-standalone-matrix.md` — fresh-operator install / usage matrix (T6) and the new FR-6 / FR-7 / FR-8 from the standalone contract
