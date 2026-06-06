# Phase 1C Implementation Notes — translation batching / verification groundwork

**Date:** 2026-06-06
**Branch:** `feature/next-wave-audit-roadmap`
**Plan:** [`2026-06-06-phase1-quick-wins-plan.md`](./2026-06-06-phase1-quick-wins-plan.md) §WS-3
**Kanban card:** `t_91f1cdde` (P1-C)

---

## 1. Scope of this wave

This card delivers the **narrow contract/validation/doc/test slice** of
Phase 1C, not the full runtime wiring. Per plan §4:

> Phase 1C — translation batching / verification groundwork
> Do third because it is the first narrow feature integration worth
> productizing, but it is still more involved than the operator UX
> batch.
> Targets:
> - define the contract
> - add validation / verification surfaces
> - document the supported path
> - only then consider deeper runtime wiring in a later phase

Everything in this wave is at the "define the contract" / "document the
supported path" layer. The runtime still calls Gemini once per file.

---

## 2. What landed

### 2.1 Contract surface — `src/dub/translator_gemini.py`

Two pure helpers + two dataclasses + two module constants were added.
**They do not call Gemini, do not depend on `TranslationConfig`, and do
not touch the runtime path.** They exist so a later phase can wire the
chunked path into `translate_srt_file` without re-litigating the
boundary.

| Symbol | Kind | Purpose |
|---|---|---|
| `TranslationBatch` | dataclass | One contiguous slice of `SubtitleBlock`s intended for a single Gemini call. Carries `index`, `blocks`, `approximate_chars`. |
| `TranslationVerification` | dataclass | Structured verification result with independent flags (`block_count_match` / `indices_preserved` / `timing_preserved`) and an `issues: list[str]`. |
| `chunk_srt_blocks(blocks, *, max_blocks=30, max_chars=4000)` | function | Greedy chunker; guarantees non-empty contiguous in-order batches; rejects `max_blocks < 1` / `max_chars < 1` / empty input with `TranslationError`. Oversized single blocks are emitted alone with a documented approximate_chars overflow. |
| `verify_translated_blocks(src_blocks, translated_texts)` | function | Three independent checks: count match, no duplicate source indices, source timing strings contain `-->`. Returns a `TranslationVerification`. |
| `DEFAULT_TRANSLATION_BATCH_BLOCKS = 30` | constant | Mirrors `defaults.tts_batch_size = 30` so the two batching surfaces feel consistent. |
| `DEFAULT_TRANSLATION_BATCH_CHARS = 4000` | constant | Per-batch character cap (≈ a conservative Gemini-2.5-flash prompt budget). |

All new symbols are exported from `__all__`.

### 2.2 Tests — `tests/test_phase1c_translation_chunking_verification.py`

15 focused tests, all passing, that lock the new contract:

* `chunk_srt_blocks` — empty-input rejection, `max_blocks=0` rejection,
  `max_chars=0` rejection, single-batch fit, `max_blocks` splitting,
  `max_chars` splitting, original-index preservation, oversized single
  block (must NOT be silently dropped), default-knob alignment with the
  TTS batch size.
* `verify_translated_blocks` — happy path, count mismatch, duplicate
  source indices, invalid source timing, combined failures, `issues`
  list shape (not a single string).

The file's module docstring explicitly documents why this is a focused
test file (new contract only) and points at the pre-existing
`test_translate_stage.py` / `test_translator_gemini.py` runtime
coverage, so a future reader does not assume the runtime path is
covered here.

### 2.3 Documentation — `docs/operator-runbook.md`

A new `### FR-7：長 SRT 翻譯（Phase 1C 合約）` section was added at the
end of §3 (最常見的錯誤情境). It does three things:

1. States the **current** behavior — single Gemini call, no batch
   switch — so operators are not misled into looking for a flag that
   does not exist yet.
2. Names the **contract surface** that is now available, so anyone
   reading the source knows where the chunker and verifier live.
3. Tells operators how to interpret the new log markers (e.g.
   `batch_index=N`) that a future runtime wave will add — without
   promising they exist today.

The numbering is local to §3 to avoid colliding with the doc-level
`FR-6`–`FR-9` sections in §4.

---

## 3. What did NOT land (intentionally)

- **No runtime wiring.** `translate_srt_file` still sends every block
  in a single Gemini call. The chunker is imported nowhere in the
  runtime path on purpose — a future phase will opt in.
- **No `TranslationConfig` knob** for batch size. Adding
  `translation.batch_size` to `config.py` would be a public contract
  change with no caller today. The defaults are exposed as module
  constants for now; the config knob can be added when runtime wiring
  lands.
- **No `dub translate` CLI subcommand.** Out of scope per plan §3.
- **No new doc-only "release notes"** — the operator runbook update is
  the only docs surface this wave touches.

---

## 4. Verification commands

Run from the repo root with the project venv:

```bash
# Focused: the new P1C contract tests (15 tests).
.venv/bin/python -m pytest tests/test_phase1c_translation_chunking_verification.py -v

# Regression: existing translation coverage must still pass.
.venv/bin/python -m pytest tests/test_translate_stage.py tests/test_translator_gemini.py tests/test_translate_mode.py -v

# Pre-commit sanity: working tree is clean after each logical commit.
git status --short   # expect empty (except the untracked phase-1 plan file, which is the plan itself)
git log --oneline -5 # expect: feat(translator) [P1C] commit, then P1B/P1A commits, then the phase-1 plan untracked
```

Expected results (verified during this wave):

* P1C contract tests: **15/15 PASSED** in 0.05s.
* Existing translation tests: **10/10 PASSED** in 0.05s.
* Working tree: clean except the untracked plan file
  `docs/plans/2026-06-06-phase1-quick-wins-plan.md`.

---

## 5. Commit log for this wave

```
639b86f feat(translator): add SRT chunking and verification contract [P1C]
70f73e7 feat(cli): state-aware recovery guidance contract [P1B]
ac25ca6 feat(cli): clarify operator route and help output [P1A]
768aa7f feat(doctor): add operator remediation guidance [P1A]
50d438f docs(readme): remove stale handoff reference and align operator truth [P1A]
```

P1C is a single commit by design: the helper contract and its tests
move together, so a future reverter can drop the whole slice as one
unit. If the runtime wiring lands in a later phase, it will get its
own commit on top of `639b86f`.

---

## 6. What the next phase (runtime wiring) should do

If/when a future card opts the runtime into the chunked path, the
minimum work is:

1. Add `TranslationConfig.batch_size: int = 30` and `.batch_chars:
   int = 4000` to `config.py` (the constants in this wave become
   fallbacks).
2. In `translate_srt_file`, after `parse_srt_blocks`, call
   `chunk_srt_blocks(blocks, max_blocks=cfg.batch_size,
   max_chars=cfg.batch_chars)`, then iterate batches and merge the
   translated lines back in source order.
3. Run `verify_translated_blocks(src_blocks, all_translated_texts)`
   before `render_srt_blocks` and fail the stage on `ok=False` with the
   `issues` list in the error message.
4. Add a focused test for the wired-up runtime path that monkey-patches
   `_call_gemini` to assert batch boundaries are respected and the
   verifier runs.
5. Update the operator runbook `### FR-7` section to flip "目前正式行為"
   from "single call" to "batched call" and describe the new log
   markers.

The contract locked in this wave means step 3 is the only place that
needs careful thought; the helpers are stable.

---

## 7. Risks and follow-ups

* **Default `max_chars = 4000` is a guess, not a measured limit.** If
  Gemini-2.5-flash starts truncating on long batches, the verifier's
  `block_count_match` flag will catch it. If it fails silently (rare),
  a runtime test using a recorded Gemini fixture would surface it.
  No action this wave; flag for the runtime-wiring card.
* **The verifier does not parse timestamps.** It only checks that the
  source timing line contains `-->`. A malformed-but-arrow-containing
  string would pass. The SRT renderer is the source of truth for
  format, and `parse_srt_blocks` would have rejected the source
  upstream, so this is acceptable for Phase 1C scope.
* **No cross-batch index test.** The verifier runs on the merged list,
  not per batch, so a per-batch renumbering bug would be caught by
  the final merged-list check, not at batch boundaries. This is
  intentional — the verifier is the post-merge gate, and a per-batch
  renumbering bug is a runtime-path concern, not a contract concern.
