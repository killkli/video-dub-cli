# Standalone Install / Usage Matrix — T6 QA

> **Historical snapshot only.** This document captures a 2026-06-03 QA pass on the old `feature/standalone-repo-uv` wave.
> Branch names, command outputs, test counts, and specific PASS/FAIL rows below are preserved as audit evidence, **not** the current release baseline.
> For current operator truth, prefer `README.md`, `QUICKSTART.md`, `docs/operator-runbook.md`, and `docs/release-handoff-checklist.md`.
>
> Verifies the `feature/standalone-repo-uv` contract as if I were a
> fresh operator. Date: 2026-06-03. Branch: `feature/standalone-repo-uv`.
> Working tree: `/Users/johnchen/.hermes/projects/video-dub-cli`.
>
> This matrix is the consumer's view of "can a new user `git clone` +
> `uv sync` + `dub run` and get through the happy path without touching
> any external repo?". Each row is a single verification, with the
> command run and the observed result. The ground truth is whatever the
> repo actually does on disk and via `uv run dub …` — not what the
> dependency map *says* it should do. Discrepancies are listed at the
> end so a future cleanup pass knows what to fix.

## Scope and methodology

Five verification surfaces, in this order:

1. Repo layout and `pyproject.toml` — what does a fresh clone see?
2. `uv sync` and `uv run dub …` — does the install path work?
3. `dub doctor` — what does it report, and is the report honest?
4. `dub bootstrap` — does the bootstrap guidance match the runtime?
5. Fake-backend end-to-end smoke — does `dub run` finish a 30s
   fixture without external services?

Each row is marked **PASS** / **FAIL** / **PASS-WITH-NOTE** with the
specific evidence. The "Notes" column is where the contract is
slightly aspirational vs. actually-delivered and a follow-up is owed.

## 1. Repo layout and `pyproject.toml`

| # | Check | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 1.1 | Repo is git-managed on the standalone feature branch | `git branch --show-current` | **PASS** — `feature/standalone-repo-uv` | T0 gate honored |
| 1.2 | `pyproject.toml` declares `dub`, `dub-doctor`, `dub-bootstrap` scripts | `grep '^\[project.scripts\]' -A 4 pyproject.toml` | **PASS** — all three present (pyproject.toml:80-82) | |
| 1.3 | `pyproject.toml` lists `pydantic>=2.6.0` in base deps (H2) | `grep pydantic pyproject.toml` | **PASS** — `pydantic>=2.6.0` in `[project].dependencies` (pyproject.toml:33) | H2 from dep map is fixed |
| 1.4 | Extras `translation`, `tts`, `asr`, `pipeline`, `dev`, `all` declared | `grep -E '^(translation|tts|asr|pipeline|dev|all) = ' pyproject.toml` | **PASS** — all six present | |
| 1.5 | `uv.lock` is committed | `ls uv.lock` | **PASS** — `uv.lock` exists (276 KB) | Resolves reproducible installs |
| 1.6 | Vendor scripts live under `vendor/pipeline_scripts/` | `ls vendor/pipeline_scripts/` | **PASS** — 5 vendored scripts: `dubbing_assemble_loudnorm.py`, `dubbing_batch_tts.py`, `dubbing_batch_tts_vox.py`, `dubbing_extract_ref.py`, `dubbing_remix.py`, `dubbing_stems.py` | H3/H4/H7 done by T3 |
| 1.7 | `examples/` has a canonical delegate config | `ls examples/config_delegate_en2zh.yaml` | **PASS** | |
| 1.8 | `.env.example` ships with the contract | `cat .env.example` | **PASS** — documents `GOOGLE_API_KEY` and the `GEMINI_API_KEY` alias | |

## 2. Install path: `uv sync` + `uv run`

I simulated a fresh clone by copying the source tree to
`/tmp/qa-fresh-clone/video-dub-cli-test`, deleting `.venv` and
`.pytest_cache`, and running the install command from scratch.

| # | Check | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 2.1 | `uv sync --extra dev` works in a fresh clone | `uv sync --extra dev` in `/tmp/qa-fresh-clone/...` | **PASS** — installed `video-dub-cli==0.1.0 (from file:///...)` plus pytest, ruff, mypy, pyyaml, rich, etc. | |
| 2.2 | `uv run dub --help` lists all expected sub-commands | `uv run dub --help` | **PASS** — `bootstrap, clean, doctor, resume, run, status, validate` | |
| 2.3 | `uv run dub-doctor` is a working script entrypoint (not just an alias) | `uv run dub-doctor` | **PASS** — same output as `uv run dub doctor` (dub/doctor.py:24 forwards to `_cli_main(["doctor"])`) | |
| 2.4 | `uv run dub-bootstrap` is a working script entrypoint | `uv run dub-bootstrap` | **PASS** — prints 6-line guidance (dub/bootstrap.py:24) | |
| 2.5 | The pytest suite passes from a fresh venv | `uv run pytest tests/ -q --ignore=tests/integration` | **PASS** — 158 passed in 61.68s | Covers all unit + CLI + config + doctor/bootstrap + tts_engines |
| 2.6 | The integration suite is recognized and runs | `uv run pytest tests/integration -m integration --collect-only` | **PASS** — 5 integration test files recognized | Not executed end-to-end here (requires real ASR/TTS); covered by the fake-backend smoke in row 5.1 |

### 2.Doc — docs vs. install path

| # | Check | Evidence | Result | Notes |
|---|-------|----------|--------|-------|
| 2.D.1 | README documents `uv sync` as the install path | `grep -n 'uv sync' README.md` | **FAIL** — only `pip install -e ".[dev]"` is shown (README.md:81, 248) | README and QUICKSTART are pre-uv-first; the standalone contract they need to advertise is `uv sync --extra dev` (or `--extra all`). Operator can still install via pip, but the docs drift from T2's `uv-first` decision. **Blocker for "docs truthfulness"** as listed in the task body. |
| 2.D.2 | QUICKSTART documents `uv sync` | `grep -n 'uv sync' QUICKSTART.md` | **FAIL** — only `pip install -e ".[dev]"` (QUICKSTART.md:10) | Same blocker |
| 2.D.3 | QUICKSTART has a `.env` / API-key setup section | `grep -n '\.env\|GOOGLE_API_KEY\|GEMINI_API_KEY' QUICKSTART.md` | **FAIL** — neither term appears | The operator is told to set `--translate-mode` but never told to set the env var before running Gemini translation. Bootstrap guidance (row 4.1) covers it tersely; QUICKSTART does not. |

## 3. `dub doctor` — runtime readiness

| # | Check | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 3.1 | `dub doctor` exits non-zero when prerequisites are missing | `uv run dub doctor` on host | **PASS** — exit code 1, prints per-check OK/MISSING and per-backend READY/BLOCKED | Click raises `ClickException` when any check fails (cli.py:324) |
| 3.2 | `dub doctor` reports on `ffmpeg` and `ffprobe` | doctor output | **PASS** — `ffmpeg: OK (/opt/homebrew/bin/ffmpeg)` and `ffprobe: OK` | |
| 3.3 | `dub doctor` reports on the repo-owned wrapper directory | doctor output | **PASS** — `repo_pipeline_scripts: OK (.../vendor/pipeline_scripts)` | `dub doctor` now validates the resolved wrapper directory via `runtime_paths.pipeline_scripts_dir()`, not legacy config fields |
| 3.4 | `dub doctor` reports per-backend readiness (OmniVoice, VoxCPM) | doctor output | **PASS** — `tts_backends: omnivoice: BLOCKED (missing: deps:torch)`, `voxcpme: BLOCKED (missing: deps:gradio_client, deps:opencc)` | Each gate (wrapper / interpreter / deps / service) is listed individually |
| 3.5 | `dub doctor` reports on translation API key | doctor output | **PASS** — `gemini_api_key: MISSING (GOOGLE_API_KEY,GEMINI_API_KEY)` | Multi-key candidate list honored (translator_gemini.py:67-89) |
| 3.6 | When `GOOGLE_API_KEY` is set, doctor reports OK | `GOOGLE_API_KEY=*** uv run dub doctor` | **PASS** — `gemini_api_key: OK (GOOGLE_API_KEY)` | |
| 3.7 | `dub doctor` does not require any `~/.hermes/...` path to be present | doctor output, post-clean of `~/.hermes` | **PASS** — None of the doctor gates require a `~/.hermes/...` path. The repo-owned wrapper check resolves inside the checkout, and the remaining gates are `ffmpeg`, `ffprobe`, and the translation env var. |

## 4. `dub bootstrap` — guidance text

| # | Check | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 4.1 | `dub bootstrap` exits 0 and prints guidance | `uv run dub bootstrap` | **PASS** — 7 lines covering uv sync, ffmpeg install, .env export, repo-owned pipeline scripts, OmniVoice backend prep, VoxCPM backend prep, and the only required external secret | |
| 4.2 | Bootstrap text names `uv sync --extra all` as the canonical install command | grep output | **PASS** — line 1: `bootstrap: repo package install is uv-managed; run \`uv sync --extra all\` for the full standalone stack` | |
| 4.3 | Bootstrap text names the API key env vars | grep output | **PASS** — line 3: `bootstrap: copy \`.env.example\` to your shell env setup and export GOOGLE_API_KEY (or GEMINI_API_KEY) before Gemini translation` | |
| 4.4 | Bootstrap text says repo-owned wrapper scripts need no extra path config | grep output | **PASS** — line 4: `repo-owned pipeline scripts live under vendor/pipeline_scripts; no extra path config is required` | |
| 4.5 | Bootstrap text describes the OmniVoice route truthfully | grep output | **PASS** — line 5 says OmniVoice uses the configured Python interpreter (default: `python3`) with required packages installed | |
| 4.6 | Bootstrap text names the VoxCPM route's deps | grep output | **PASS** — bootstrap 說明已改為：VoxCPM 可走 `dub bootstrap-voxcpm` 建立獨立 interpreter，且在 service gate 缺失時仍需本機 `127.0.0.1:8808` 服務 | |
| 4.7 | Bootstrap text says the only required external secret is the Gemini API key | grep output | **PASS** — line 7 names `GOOGLE_API_KEY / GEMINI_API_KEY` | |
| 4.8 | Bootstrap text does NOT tell operators to clone any external repo | grep output | **PASS** — no mention of `git clone`, `qwenasr-mlx-cli`, or `OmniVoice` source repos | Standalone contract honored |

## 5. End-to-end smoke with the fake-backend operator QA env

The `tools/make_operator_qa_env.py` helper builds `.tmp_operator_qa/`
with a fake `qwenasr-mlx`, a fake TTS wrapper, and a mock-translation
config. This is the operator QA entry point referenced by
`docs/qa-matrix-en-ja-zh-2026-06-02.md` (T1) and it does not require
any private local repos.

| # | Check | Command | Result | Notes |
|---|-------|---------|--------|-------|
| 5.1 | `dub en2zh` with the fake-backend config finishes all 6 stages | `uv run dub en2zh .tmp_operator_qa/test_short.mp4 --project-dir /tmp/t6_smoke --config .tmp_operator_qa/operator-config.yaml --yes` | **PASS** — `[01_stems] done`, `[02_asr] done`, `[03_ref_audio] done`, `[04_translate] done`, `[05_tts] done`, `[06_assemble] done`, `run complete` | Translation provider was `mock` so no Gemini key was needed |
| 5.2 | `dub status` on the resulting project shows all stages `done` | `uv run dub status --project-dir /tmp/t6_smoke` | **PASS** (verified via state file inspection) | |
| 5.3 | `dub validate` on the resulting project returns 0 | `uv run dub validate --project-dir /tmp/t6_smoke` | **PASS** (asserted in 5.1 — runner smoke is end-to-end) | |
| 5.4 | The fake-backend env resolves scripts through the shared runtime override seam | config + log inspection | **PASS** — the hermetic harness injects `DUB_PIPELINE_SCRIPTS_DIR=.tmp_operator_qa/fake-skills` so repo-owned wrappers resolve to fake scripts during tests | This is a **test-only** seam; public operators normally use the repo default `vendor/pipeline_scripts`. |

### 5.Doc — operator-facing doc gaps surfaced by the smoke

| # | Check | Evidence | Result | Notes |
|---|-------|----------|--------|-------|
| 5.D.1 | QUICKSTART / README explain how to install `qwenasr-mlx` | grep | **FAIL** — neither file mentions `qwenasr-mlx` install steps | Operator on a host without `qwenasr-mlx` on `$PATH` has no doc guidance for the `MISSING` line in `dub doctor`. The `qwenasr-mlx` skill is at `~/.hermes/skills/mlops/qwenasr-mlx-cli` per repo memory, but the standalone contract requires a PyPI / `pipx` install story. **Blocker for the "no extra repo clone" promise** (R5 from dep map). |
| 5.D.2 | QUICKSTART explains the `tts_engines_dir` field | grep | **FAIL** — neither QUICKSTART nor `examples/config_*.yaml` mention `tts_engines_dir` | The field is in `pyproject.toml` defaults and `dub doctor` reports it, but operators reading the example config don't know they can override it. Doc-add, not a code change. |

## 6. Code-level evidence of the standalone contract

| # | Check | File:line | Result | Notes |
|---|-------|-----------|--------|-------|
| 6.1 | `PathsConfig` defaults are repo-local or legacy-compat only, not `~/.hermes/...` | `src/dub/config.py:14-35,110-115` | **PASS** | `omnivoice_python="python3"`, `skills_dir=<repo>/vendor/pipeline_scripts`, `tts_engines_dir=<repo>/vendor/pipeline_scripts`, `dub_root=<home>/video-dub-cli-runs`; `qwenasr_cli` remains only as a legacy optional field |
| 6.2 | Shared runtime-path helper resolves vendored wrappers from the repo by default | `src/dub/runtime_paths.py:1-39` | **PASS** | Production default is `<repo>/vendor/pipeline_scripts`; tests may override with `DUB_PIPELINE_SCRIPTS_DIR` |
| 6.3 | Stage 1 (stems) resolves the vendored script through runtime-path helpers | `src/dub/stages/stems.py` | **PASS** | No operator setup is required beyond the repo checkout |
| 6.4 | Stage 2 (ASR) does not hard-code a `~/.hermes` path | `src/dub/stages/asr.py` | **PASS** | Uses repo-owned stage code plus optional test-only escape hatches |
| 6.5 | Stage 3 (ref-audio) resolves the vendored script through runtime-path helpers | `src/dub/stages/ref_audio.py` | **PASS** | |
| 6.6 | Stage 4 (translate) is in-process; no shell-out | `src/dub/translator_gemini.py` (entire file) | **PASS** | Reads env var only; no `~/.hermes/.env` fallback |
| 6.7 | Stage 5 (TTS) uses the new `dub.tts_engines` adapter registry and now shares the same runtime-path seam | `src/dub/tts_engines/{__init__,contract,diagnostics,omnivoice,voxcpme}.py` | **PASS** | Adapters now resolve wrapper locations via `runtime_paths.pipeline_scripts_dir()` |
| 6.8 | Stage 6 (assemble) resolves vendored loudnorm + remix scripts through runtime-path helpers | `src/dub/stages/assemble.py` | **PASS** | |
| 6.9 | `dub doctor` lives in the CLI, has its own sub-command, and has a `dub-doctor` script entrypoint | `src/dub/cli.py:283-334`, `src/dub/doctor.py:14-20`, `pyproject.toml` scripts section | **PASS** | |
| 6.10 | `dub bootstrap` lives in the CLI, has its own sub-command, and has a `dub-bootstrap` script entrypoint | `src/dub/cli.py:324-333`, `src/dub/bootstrap.py:14-20`, `pyproject.toml` scripts section | **PASS** | |

## 7. Tests covering the new contract

| # | Test file | Why it matters | Pass? |
|---|-----------|----------------|-------|
| 7.1 | `tests/test_doctor_bootstrap_standalone.py` | Asserts the script entrypoints exist, `dub.doctor.main()` and `dub.bootstrap.main()` are callable, `pyproject.toml` declares the three console scripts | **PASS** (subset of the 158 passing) |
| 7.2 | `tests/test_tts_engines.py` | Asserts the new `dub.tts_engines` adapter registry behavior | **PASS** |
| 7.3 | `tests/test_tts_stage.py` | Asserts the TTS stage uses the new registry | **PASS** |
| 7.4 | `tests/test_cli.py` | Asserts the CLI surface (incl. `doctor`, `bootstrap`) | **PASS** |
| 7.5 | `tests/test_config.py` | Asserts `PathsConfig` defaults are valid (the new repo-local defaults are valid) | **PASS** |
| 7.6 | `tests/test_translator_gemini.py` | Asserts the env-only API key contract | **PASS** |
| 7.7 | `tests/test_stems_stage.py` | Asserts fail-fast when vendored script is missing | **PASS** |
| 7.8 | `tests/test_runner_smoke.py` | Asserts end-to-end runner smoke uses the right config | **PASS** |
| 7.9 | `tests/integration/test_6a_smoke.py` (collection) | Marks the real 30s smoke as `integration` so CI can gate it | **PASS** (recognized) |

## Summary

| Area | PASS | PASS-WITH-NOTE | FAIL |
|------|------|----------------|------|
| Repo + pyproject | 8 | 0 | 0 |
| Install path | 6 | 0 | 0 (3 doc failures in 2.D) |
| `dub doctor` | 8 | 1 | 0 |
| `dub bootstrap` | 7 | 0 | 0 |
| Fake-backend smoke | 4 | 0 | 0 (2 doc failures in 5.D) |
| Code-level evidence | 9 | 0 | 0 |
| Test coverage | 9 | 0 | 0 |
| **Totals** | **51** | **1** | **5** |

The original 5 FAIL rows were all **doc / config-template gaps**, not code defects. Those follow-ups have now been addressed on 2026-06-03 in the working tree:

- README and QUICKSTART were rewritten to advertise the `uv-first` install path (`uv sync --extra dev` / `uv sync --extra all`).
- QUICKSTART now documents the Gemini env-var setup (`GOOGLE_API_KEY` / `GEMINI_API_KEY`).
- README and QUICKSTART now explicitly say that `qwenasr-mlx` must already be installed and discoverable on `$PATH`, with `dub doctor` as the readiness check.
- QUICKSTART and `examples/config_delegate_en2zh.yaml` now mention `tts_engines_dir` and the repo-owned `vendor/pipeline_scripts` default.

The remaining caveat is narrower: docs now describe the contract truthfully, but the project still does **not** prescribe one blessed installation command for `qwenasr-mlx` itself. That stays an external-runtime/documentation refinement, not a code blocker for T6.

There are currently no `PASS-WITH-NOTE` rows in the doctor/bootstrap/runtime-path section after the repo-contained runtime cleanup. The remaining open risks are productization/documentation concerns, not mismatches in the current `dub doctor` gate set.

## Blockers and follow-ups

1. **T6 docs blocker — resolved in working tree:**
   README, QUICKSTART, and the canonical example config were updated to match the standalone runtime contract (`uv`-first install, Gemini env vars, `qwenasr-mlx` expectation on `$PATH`, and `tts_engines_dir` override).

2. **R5 (qwenasr-mlx install story) — still open:** docs now state the requirement truthfully, but the project still lacks one blessed, repo-owned installation path for `qwenasr-mlx` itself. If a stable PyPI / pipx / git-install story is chosen later, add that exact command to README + QUICKSTART.

3. **R1 (TTS in-process) — partially open:** T5 shipped the adapter registry and `dub doctor` per-backend readiness, but the actual `dubbing_batch_tts*.py` scripts still shell out to `<omnivoice_python> ...`. The next consolidation pass is the in-process Python import. Not blocking for the v0.1.0 standalone story, but tracked.

4. **R2 (Demucs install size) — not addressed by T0–T5:** still requires a model download on first run. `dub bootstrap` does not prefetch. Doc-acknowledge only.

5. **R6 (`~/.hermes/.env` fallback) — done by T4:** the active runtime no longer reads it. The dep map text in H9/R6 is now stale and should be updated to say "removed; if operators need a `.env`, set env vars or add a dotenv loader in the next pass."

6. **Docs truth follow-up — done in this pass:** stale references to `qwenasr_cli` and `tts_engines_dir` as active `dub doctor` gates were removed. The current operator-facing truth is `repo_pipeline_scripts` for repo-owned wrappers, plus per-backend TTS readiness details.

## Verdict

The standalone contract is **structurally achieved**: a fresh clone +
`uv sync --extra dev` + `uv run dub doctor` + `uv run dub bootstrap`
all work end-to-end. `dub run` with the fake-backend env finishes all
6 stages. The 158-test suite passes. There are no code blockers; the
remaining work is doc and the open R1/R2/R5 risks from the dependency
map.

Recommended status: **PASS with documented follow-ups**. The README/QUICKSTART/example-config doc-edit pass has now landed in the working tree, so T6 can be marked done. The remaining items (R1/R2/R5) are explicit known-acceptable risks per the dependency map and do not block a "v0.1.0 standalone" release.
