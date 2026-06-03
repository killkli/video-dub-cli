# video-dub-cli Standalone Repo + UV Consolidation Plan

> For Hermes: execute via Kanban with explicit dependency links. Goal state is: user clones this repo, installs Python/uv-managed environment, runs bootstrap/install steps documented here, and can use the full CLI without cloning any other repo.

**Goal:** Remove runtime code dependencies on external repos / Hermes skills so `video-dub-cli` becomes a self-contained repository with a UV-managed Python environment and in-repo implementation of every pipeline stage.

## Scope upgrade — 2026-06-03 second wave

User requirement tightened after the first standalone pass:

- **All executable runtime code should live in this repo**.
- Operators should **not** have to configure `qwenasr_cli`, `tts_engines_dir`, or other script-path settings.
- The **only required external configuration** should be the translation key:
  `GOOGLE_API_KEY` / `GEMINI_API_KEY`.

This changes the target from "no extra repo clone" to the stronger
contract "repo-contained runtime code + explicit system/model deps".

### New canonical interpretation

- `ffmpeg` / `ffprobe` may remain system binaries.
- Model weights / caches may remain bootstrap assets.
- But **runtime Python code and wrapper scripts** for ASR, TTS, assemble,
  remix, and stage orchestration must be repo-owned.
- Config should converge toward *no operator-managed path knobs* except
  project/output choices and translation API key.

### Immediate implementation order

1. Remove `tts_engines_dir` from the operator story by resolving TTS
   wrappers from repo-owned vendored paths only.
2. Vendor `qwenasr-mlx-cli` package code into this repo and replace the
   external `qwenasr-mlx` command dependency with an in-repo module / CLI.
3. Collapse remaining legacy path fields (`skills_dir`, `qwenasr_cli`,
   `omnivoice_python`) into compatibility-only internals, then remove them
   from user-facing docs/config examples.
4. Re-run operator QA against the stricter contract.

**Architecture:** Vendor or reimplement all currently external stage scripts inside this repo under first-class package/module ownership. Replace `config.paths.skills_dir`, external `subtitle_translation.py`, and external repo python executables with in-repo modules, console commands, or optional extras. Keep unavoidable non-Python system tools explicit (`ffmpeg`, optionally `yt-dlp`) and provide bootstrap/doctor checks so operators know exactly what remains system-level.

**Non-goal:** Shipping model weights inside git. Heavy models / checkpoints may still be first-run downloads or bootstrap assets, but no separate source repo clones should be required.

**Key external dependency hotspots discovered:**
- `src/dub/config.py`
  - `qwenasr_cli` defaults to `~/.hermes/projects/qwenasr-mlx-cli/.venv/bin/qwenasr-mlx`
  - `omnivoice_python` defaults to `~/Dev/OmniVoice/.venv/bin/python3`
  - `skills_dir` defaults to `~/.hermes/skills/media/video-dubbing-pipeline/scripts`
  - `translation_skill` defaults to `~/.hermes/skills/media/subtitle-translation/subtitle_translation.py`
- `src/dub/stages/stems.py` shells out to external `dubbing_stems.py`
- `src/dub/stages/ref_audio.py` shells out to external `dubbing_extract_ref.py`
- `src/dub/stages/tts.py` shells out to external `dubbing_batch_tts.py` / `dubbing_batch_tts_vox.py`
- `src/dub/stages/assemble.py` shells out to external `dubbing_assemble_loudnorm.py` / `dubbing_remix.py`
- `src/dub/translator_gemini.py` still reads API keys from `~/.hermes/.env`
- `pyproject.toml` currently lacks required runtime deps for Gemini / opencc / gradio / audio stack / packaging support for standalone execution

**Target packaging contract:**
- `uv sync` installs everything this repo owns.
- `uv run dub ...` is the primary operator path.
- In-repo modules replace skill-script path dispatch.
- `uv run dub doctor` validates system commands, model availability, and required env vars.
- `uv run dub bootstrap` optionally prepares caches / downloads / model setup that cannot live in git.
- Example configs and docs only point to repo-local defaults.

---

## Work graph

### T0. Create standalone feature branch
Create `feature/standalone-repo-uv` from current main. All subsequent work lands there.

### T1. Architecture + dependency inventory (Research)
Produce a canonical dependency map:
- which modules are still external code
- which ones should be vendored verbatim vs reimplemented as package modules
- which system dependencies remain outside Python (`ffmpeg`, optional `yt-dlp`)
- which Python deps belong in base install vs optional extras
Deliverable: `docs/standalone-dependency-map.md`

### T2. Packaging skeleton + UV contract (Dev)
Implement repo-level packaging changes:
- move from minimal setuptools-only packaging to UV-first developer/operator workflow
- expand `pyproject.toml` deps/extras/scripts
- add `uv.lock` if appropriate in this environment
- add bootstrap/doctor CLI entrypoints scaffold
Deliverable: packaging skeleton committed and tests updated.

### T3. Vendor/inline non-TTS stage scripts (Dev)
Bring these into repo-owned code paths:
- stems
- ref-audio extraction
- assemble loudnorm builder
- remix
Replace `skills_dir` dependence for these stages.
Deliverable: stage modules call in-repo code only for stages 1, 3, 6.

### T4. Vendor/inline translation stage + env contract (Dev)
Finish standalone Gemini translation path:
- remove `translation_skill` legacy dependence from active runtime
- replace `~/.hermes/.env` coupling with explicit env loading contract / `.env.example` / docs
- ensure mock mode and tests pass under repo-only environment
Deliverable: translation runs from repo-only code with documented env setup.

### T5. TTS backend consolidation design + first implementation wave (Dev)
Most complex lane. Decide packaging/integration path for:
- OmniVoice route
- VoxCPM route
- any local-server assumptions
Need first workable repo-only strategy, e.g. vendored adapters + optional extras + bootstrap/setup docs. If a full pure-repo embed is too large, the acceptable contract is still "no extra repo clone" via PyPI package / wheel / submodule-free vendored code.
Deliverable: documented and partially implemented consolidated TTS integration contract.

### T6. QA matrix for standalone install (QA)
Validate on fresh-ish env assumptions:
- clone repo
- `uv sync`
- `uv run dub doctor`
- smoke route(s) with fake backends
- operator docs truthful about remaining non-git prerequisites
Deliverable: `docs/qa-standalone-matrix.md`

### T7. Docs / onboarding rewrite (Writer)
Rewrite README / QUICKSTART / operator runbook around standalone contract.
Deliverable: docs that say exactly what a new user must install and nothing else.

### T8. Final integration + truthfulness gate (Dev)
Merge outputs from T1–T7, close remaining gaps, run full tests, and prepare branch for user review.

---

## Dependency edges
- T0 -> T1, T2, T5
- T1 -> T3, T4, T6, T7
- T2 -> T3, T4, T5
- T3 + T4 + T5 -> T6
- T1 + T6 -> T7
- T3 + T4 + T5 + T6 + T7 -> T8

## Acceptance criteria
- No runtime stage in normal CLI path depends on `~/.hermes/skills/...` code.
- No runtime stage requires cloning another source repo.
- `uv run dub --help` and `uv run dub doctor` work in repo-only environment.
- Docs explicitly enumerate remaining non-Python system dependencies.
- Regression tests pass; standalone QA artifact produced.
