# Operator Runbook — Failure Recovery Guide

**Date:** 2026-06-02
**Scope:** Recovery procedures for `video-dub-cli` pipeline failures.
**Reference:** QA matrix at `docs/qa-matrix-en-ja-zh-2026-06-02.md`.

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
| Pipeline stopped mid-run (stage status = `running`) | `dub resume` |
| A specific stage failed but earlier stages are fine | `dub clean --project-dir <path> --stage <N>` then `dub resume` |
| Want to re-run from scratch without touching source | `dub clean --project-dir <path>` then re-run `dub run` |

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
# Provide the path and re-run:
dub run <video> \
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
dub run <video> \
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
dub run <video> \
  --source-lang en \
  --target-lang zh \
  --translate-mode use-existing \
  --translated-srt /path/to/translated.srt

# Option B: let CLI translate (delegate mode, default)
dub run <video> --source-lang en --target-lang zh
```

---

### FR-4: Stage 5 (TTS) OOM or subprocess crash

**Symptoms:** Stage 5 halts with `status: failed`, `error: OOM` or similar in `.dub/05_tts.log`.

**Recovery:**
```bash
# Step 1: check current state
dub status --project-dir <path>

# Step 2: resume — re-enters at the failed stage
dub resume --project-dir <path>
```

The TTS stage has built-in per-line recovery: if some `line_<i>_tts.wav` files are missing or undersized after a failure, the stage will re-invoke TTS scoped to each missing cue via `--start N --end N`.

---

### FR-5: Stage 6 (assemble) ffprobe failure

**Symptoms:** Stage 6 halts with `status: failed`. ffprobe cannot read the output MP4, or the subprocess exited non-zero.

**Recovery:**
```bash
# Step 1: check state
dub status --project-dir <path>

# Step 2: clean only stage 6 artifacts (keeps earlier stages intact)
dub clean --project-dir <path> --stage 6

# Step 3: resume
dub resume --project-dir <path>
```

`--stage 6` only removes artifacts from `07_final/`. Your earlier stages (`01_stems` through `06_tts_wav`) are preserved.

---

## Known Fragility (from T3 research)

These coupling weaknesses are known and not yet hardened:

### Weakness 1 — `source_lang` is dual-role but not locked per project

`source_lang` simultaneously controls ASR language and TTS script route. If you resume a project with a different config (or a future version adds a new language route), the pipeline may re-enter with a different ASR language or TTS script, causing inconsistency with already-existing artifacts.

**Operational mitigation:** Always use the same `--source-lang` when resuming a project. Do not mix `--source-lang en` first-run with `--source-lang ja` resume.

### Weakness 2 — `TranslationConfig.provider` is a weak contract

The config field `provider: gemini` looks like a configurable route, but the stage code does not dispatch on it — it always calls `translate_srt_file` (Gemini) unless `provider == "mock"`. Switching to another backend via config will not work as expected.

**Operational mitigation:** Do not change `translation.provider` in config — only `gemini` and `mock` are supported.

### Weakness 3 — Dual translated SRT paths

Canonical path: `05_translated_srt/video.zhtw.srt`
Legacy compat copy: `05_translate/video.zhtw.srt`

Both are written by the translate stage. `validate` and `skip` only check the canonical path. The compat copy exists for legacy tool compatibility and may be removed in future versions without notice.

**Operational mitigation:** Treat `05_translated_srt/video.zhtw.srt` as the only stable contract. Do not reference `05_translate/video.zhtw.srt` in external tooling.

---

## Quick Reference: CLI Commands

```bash
# Run pipeline
dub run <video> --source-lang en --target-lang zh

# Check status
dub status --project-dir <path>

# Validate outputs
dub validate --project-dir <path>

# Resume after failure
dub resume --project-dir <path>

# Clean stage N then resume
dub clean --project-dir <path> --stage N
dub resume --project-dir <path>

# Full clean (keeps source video)
dub clean --project-dir <path>

# Read state
cat .dub/state.json | python3 -m json.tool

# Tail a stage log
tail -30 .dub/05_tts.log
```

---

## Full QA Matrix

For the complete test matrix including all five route scenarios (Rows 1–5) and five failure-recovery scenarios (FR-1 through FR-5), see `docs/qa-matrix-en-ja-zh-2026-06-02.md`.