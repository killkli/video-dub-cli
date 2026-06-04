# Auto Workflow Wave 2 — Kanban Execution Plan

> **For Hermes:** use this document as the execution contract for the next development wave after `dub auto` + smoke + docs alignment have already landed on `main`.

**Goal:** continue productizing `video-dub-cli` so an operator can hand one video to the CLI and get a truthful, resumable, low-friction EN→ZH / JA→ZH workflow with an obvious default project location, zero-conf common path, and recovery tools that remain explicit.

**Architecture:** keep the staged pipeline and verified `dub auto` surface, but reduce operator decision load on the common path. The next wave is about contract tightening, not replacing the stage runner.

**Tech stack:** Python 3.11+, Click CLI, pytest, `ProjectState`, existing `dub doctor` / `resume` / `validate` flow, Kanban board `video-dub-cli-auto-workflow`.

---

## Grounded baseline at start of Wave 2

Verified on 2026-06-04 in `/Users/johnchen/.hermes/projects/video-dub-cli`:

- Active branch: `main`
- Latest merged commit: `e9ac097` (`docs: align auto workflow docs with smoke-tested contract`)
- Canonical commands already exist:
  - `uv run dub auto <video>`
  - `uv run dub en2zh <video>`
  - `uv run dub ja2zh <video>`
  - `uv run dub resume --project-dir <dir>`
  - `uv run dub status --project-dir <dir>`
  - `uv run dub validate --project-dir <dir>`
- Existing auto-workflow board state:
  - T0–T11 all done
  - no ready/todo cards remain on `video-dub-cli-auto-workflow`
- Current open gap from T1 audit remains real:
  - common commands still expose too much control surface
  - default project location still feels implicit
  - docs are now smoke-aligned, but product contract is not yet fully collapsed to a true zero-friction operator path

---

## Why Wave 2 exists

Wave 1 proved the workflow is real.
Wave 2 makes it feel like a finished operator product.

The user request is not merely “have a pipeline”; it is “CLI 輸入影片後，自動把後面的流程全部跑完,” with a full Kanban development cycle. That means the next work should focus on the remaining friction between:

1. a working engineering surface, and
2. an obvious operator surface.

---

## Scope of Wave 2

### In scope

1. Collapse the common path for `en2zh` / `ja2zh` further toward zero-conf defaults.
2. Make default project location obvious and testable.
3. Ensure command output tells the operator exactly where project state and final output live.
4. Add regression coverage for no-flag common-path behavior.
5. Update docs only where runtime contract actually changes.

### Out of scope

1. ML-based automatic language detection.
2. Replacing the existing stage architecture.
3. Unifying OmniVoice and VoxCPM into one Python environment.
4. Broad backend expansion unrelated to the one-video → one-workflow operator contract.

---

## Wave 2 deliverables

### D1. Clear default project-dir contract
When the operator omits `--project-dir`, the CLI should either:
- derive an obvious project directory from the input video path, or
- print the exact chosen project directory before expensive work starts.

Acceptance truth:
- operator does not need to inspect config internals to find outputs.

### D2. Zero-conf common-path verification
At least one smoke/regression path should prove:
- `dub en2zh <video>` works with only a video path under supported config/default assumptions, or
- if a config/default dependency remains required, the CLI says so explicitly before stage work begins.

### D3. Recovery visibility
The common-path command must make post-run recovery obvious by printing or logging:
- project directory
- final output path
- next-step recovery hints (`resume`, `status`, `validate`)

### D4. Docs stay downstream of runtime truth
README / QUICKSTART / runbook should only change after runtime behavior is verified.

---

## Task graph

### T12 — Gate / baseline freeze
**Assignee:** `default`
**Purpose:** freeze the Wave 2 starting point on top of merged `main`, confirm no hidden board debt remains, and capture the exact contract we are about to tighten.

Outputs:
- verification note in plan / board summary
- current `main` SHA
- confirmation that `video-dub-cli-auto-workflow` has no unfinished tasks

### T13 — Research: zero-conf common-path contract
**Assignee:** `kanban-research`
**Depends on:** T12
**Purpose:** inspect `src/dub/cli.py`, `src/dub/config.py`, and the existing gap-analysis docs; propose the narrowest runtime change that makes `en2zh` / `ja2zh` feel truly one-shot without breaking explicit controls.

Must answer:
- what exact behavior should happen when `--project-dir` is omitted?
- what exact output should be printed so the operator can recover later?
- what should remain configurable but de-emphasized?

### T14 — Dev: implement default project-dir / output visibility contract
**Assignee:** `default`
**Depends on:** T12, T13
**Purpose:** implement the narrow runtime slice from T13.

Expected areas:
- `src/dub/cli.py`
- possibly `src/dub/config.py`
- tests for the new default path / output messaging behavior

Must include:
- targeted tests first or in the same slice
- real verification commands
- minimal logical commits

### T15 — QA: zero-conf and recovery-path verification
**Assignee:** `kanban-qa`
**Depends on:** T14
**Purpose:** verify the post-change operator experience on the common path.

Checks:
- help text remains truthful
- no-flag / low-flag invocation behavior is consistent with contract
- project directory is discoverable
- final artifact / state / recovery commands are discoverable
- any mismatch is reported as a contract bug, not hand-waved away

### T16 — Docs: only update operator-facing wording after QA truth
**Assignee:** `kanban-writer`
**Depends on:** T15
**Purpose:** update docs if and only if runtime/QA confirm a changed contract.

Likely files:
- `README.md`
- `QUICKSTART.md`
- `docs/operator-runbook.md`

---

## Execution rules

1. Use the existing board: `video-dub-cli-auto-workflow`.
2. Do not create a new board unless Wave 2 scope changes materially beyond operator-contract tightening.
3. All code-changing tasks must commit at minimal logical granularity.
4. Every code or docs claim must be backed by real command output.
5. QA should verify artifacts / state / output messages, not just exit codes.
6. Documentation follows runtime truth, not the other way around.

---

## Verification commands

Baseline / discovery:

```bash
git branch --show-current
git status --short
git log --oneline -3
hermes kanban --board video-dub-cli-auto-workflow list
```

CLI surface:

```bash
uv run dub --help
uv run dub auto --help
uv run dub en2zh --help
uv run dub ja2zh --help
uv run dub doctor
```

Targeted tests (shape only; exact subset may tighten after T13):

```bash
pytest -q tests/test_cli.py
```

Smoke / operator path (if supported by contract):

```bash
uv run dub en2zh <video>
uv run dub status --project-dir <dir>
uv run dub validate --project-dir <dir>
```

---

## Completion criteria for Wave 2

Wave 2 is done only if all of the following are true:

- the common path is more obvious than Wave 1, not just differently documented
- default project/output location is either deterministic or explicitly surfaced before expensive work
- operator can discover recovery commands and paths without reading source
- tests cover the new contract
- docs match verified runtime behavior
