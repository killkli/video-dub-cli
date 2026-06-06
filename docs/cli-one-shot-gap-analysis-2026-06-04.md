# CLI one-shot gap analysis (T1 audit, 2026-06-04)

> **Historical gap audit.** This document captures what was still missing during the 2026-06-04 feature-wave audit.
> Items below may already be fixed; treat this file as audit history, not as the current defect list.

## Scope

Audit the current `dub` CLI against the desired one-shot operator workflow for the standalone repo contract.

Repo inspected: `/Users/johnchen/.hermes/projects/video-dub-cli`
Branch: `feature/standalone-repo-uv`

## What the current CLI already gives us

The current CLI already has the main pieces of an operator workflow:

- `dub en2zh <VIDEO>` and `dub ja2zh <VIDEO>` exist as the language-specific entrypoints.
- `dub run <VIDEO>` exists as the explicit/base entrypoint.
- `dub resume --project-dir <DIR>` preserves resumability from saved state.
- `dub status`, `dub validate`, `dub clean`, `dub doctor`, and `dub bootstrap` are all first-class commands.
- `dub doctor` already acts as the canonical readiness gate for the standalone stack and reports backend readiness.
- The pipeline itself is already artifact-driven and resumable.

## What is still implicit or still forces operator thought

### 1) The one-shot commands still expose too much control surface

`en2zh` and `ja2zh` are present, but they still accept the same operational knobs as `run`:

- `--project-dir`
- `--config`
- `--translate-mode`
- `--translated-srt`
- `--vocal-gain`
- `--inst-gain`
- `--keep-fulltrack`
- `-y/--yes`

That means the operator still has to think about pipeline internals in the common case.

### 2) `run` is still presented as a normal first-class route

`dub run` is valuable as an escape hatch, but the docs still show it as a normal supported path early and often. That weakens the one-shot story because the default mental model remains “pick flags,” not “give video to the lane-specific command.”

### 3) Project location is still not fully collapsed into a one-shot default

Current behavior creates or reuses a project directory under `cfg.paths.dub_root` when `--project-dir` is omitted. That is workable, but it still leaves the user guessing where the output will land unless they already know the repo convention.

The target contract should make the project location obvious from the input video and/or document the default path up front, so the operator does not have to infer it from config.

### 4) Config defaults still carry legacy/implicit baggage

`src/dub/config.py` still contains path defaults that encode old compatibility assumptions, including:

- `paths.qwenasr_cli`
- `paths.omnivoice_python`
- `paths.skills_dir`
- `paths.translation_skill`
- `paths.dub_root`

Even though some of these are now compatibility shims, the schema still makes the operator think about path plumbing and legacy locations.

### 5) Resume/debug still requires the operator to know the project directory

`dub resume` and `dub status` are intentionally explicit, but they still require the operator to know the project path. That is fine for recovery, but it means the one-shot path needs very clear output so the operator can find the project and final artifact without inspecting implementation details.

## What is already automatic vs what is still implicit

Automatic today:

- Stage execution order is fixed by the runner.
- Stage outputs are persisted on disk.
- `dub doctor` checks system dependencies, API keys, repo pipeline scripts, and backend readiness.
- `dub doctor` auto-recovers Gemini key values from shell rc files when possible.
- `dub resume` restores state-derived routing information from saved project state.
- `translate_mode=delegate` is already the default for the happy path.

Still implicit / operator-dependent today:

- Which flags are necessary versus optional for the common case.
- Where the project directory should live if the user does not specify one.
- Which command is the “right” one for first-time operators versus advanced operators.
- Whether a missing prerequisite should be handled by `doctor` first or by trying `run` and reading the error.

## Gap to the desired one-shot contract

Desired contract from the T0 board note:

- `dub en2zh <VIDEO>` / `dub ja2zh <VIDEO>` should be the zero-flag default for the common case.
- `dub doctor` should be the canonical pre-flight for the auto path.
- `dub run` should remain available only as the explicit-control escape hatch.
- README / QUICKSTART should lead with the one-shot path, not the low-level path.

Current state does not yet fully meet that because the common commands still present too much pipeline control surface and the docs still make `run` feel equally primary.

## Recommended first implementation slice

Do the smallest change that makes the one-shot contract feel real without removing the advanced escape hatch:

1. Collapse the common path defaults for `en2zh` / `ja2zh`.
   - Derive source/target languages from the subcommand.
   - Default project location and config behavior so the operator can run the command with only a video path.
   - Keep `run` for explicit overrides only.

2. Make `doctor` speak the auto-workflow language.
   - It should clearly tell the operator whether the machine is ready for `dub en2zh` / `dub ja2zh`.
   - Missing prerequisites should map to the same auto path defaults, not just the legacy `run` path.

3. Update the docs to match the operator mental model.
   - First-screen guidance should be one-shot usage.
   - `run` should be documented as the advanced escape hatch.
   - `resume`, `status`, and `doctor` should stay visible as recovery tools.

4. Add or update a smoke test that proves the one-shot command works with the new defaults.
   - The test should exercise `dub en2zh <sample.mp4>` or `dub ja2zh <sample.mp4>` without extra flags.
   - It should verify the project/output contract and that the run is resumable.

## Exact files inspected

- `src/dub/cli.py`
- `src/dub/config.py`
- `src/dub/doctor.py`
- `src/dub/bootstrap.py`
- `README.md`
- `QUICKSTART.md`
- `docs/auto-workflow-contract-2026-06-04.md`
- `docs/operator-runbook.md`
- `docs/standalone-dependency-map.md`
- `docs/operator-qa-supported-flow-2026-06-02.md`
- `pyproject.toml`

## Commands used to verify the current CLI surface

```bash
cd /Users/johnchen/.hermes/projects/video-dub-cli
uv run dub --help
uv run dub en2zh --help
uv run dub run --help
uv run dub resume --help
uv run dub doctor --help
```

## Recommendation for T3

T3 should implement the default-collapsing slice first, then update the operator-facing docs and smoke test in the same change set. That is the smallest honest cut that makes the one-shot workflow feel like the default without breaking the advanced `run` escape hatch.
