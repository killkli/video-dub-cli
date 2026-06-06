"""Phase 1C — translation batching / verification groundwork.

Locks in the narrow contract slice from
``docs/plans/2026-06-06-phase1-quick-wins-plan.md`` §WS-3:

* ``chunk_srt_blocks`` returns non-empty, contiguous, in-order batches
  that respect both the per-batch block limit and the per-batch
  character cap, with documented behavior for single oversized blocks
  and explicit errors for bad inputs.
* ``verify_translated_blocks`` produces a structured
  ``TranslationVerification`` that distinguishes block-count mismatch,
  index/duplicate problems, and source-timing corruption so callers
  can route failures to the right recovery path.
* Both helpers are PURE — they do not call Gemini and do not depend
  on ``TranslationConfig`` — so a later runtime wave can wire them
  into ``translate_srt_file`` without re-litigating the boundary.

These tests are intentionally focused on the new helpers only. The
existing ``test_translate_stage.py`` and ``test_translator_gemini.py``
coverage of the runtime Gemini path is left untouched so the single
commit introduces a clean contract surface, not a runtime refactor.
"""

from __future__ import annotations

import pytest

from dub.errors import TranslationError
from dub.translator_gemini import (
    DEFAULT_TRANSLATION_BATCH_BLOCKS,
    DEFAULT_TRANSLATION_BATCH_CHARS,
    SubtitleBlock,
    TranslationBatch,
    TranslationVerification,
    chunk_srt_blocks,
    verify_translated_blocks,
)


# ---------------------------------------------------------------------------
# chunk_srt_blocks
# ---------------------------------------------------------------------------


def _block(i: int, text: str) -> SubtitleBlock:
    return SubtitleBlock(index=i, timing=f"00:00:{i:02d},000 --> 00:00:{i:02d},500", text=text)


def test_chunk_srt_blocks_empty_input_raises():
    with pytest.raises(TranslationError, match="cannot chunk an empty block list"):
        chunk_srt_blocks([])


def test_chunk_srt_blocks_rejects_zero_max_blocks():
    blocks = [_block(1, "hi")]
    with pytest.raises(TranslationError, match="max_blocks must be >= 1"):
        chunk_srt_blocks(blocks, max_blocks=0)


def test_chunk_srt_blocks_rejects_zero_max_chars():
    blocks = [_block(1, "hi")]
    with pytest.raises(TranslationError, match="max_chars must be >= 1"):
        chunk_srt_blocks(blocks, max_chars=0)


def test_chunk_srt_blocks_single_batch_when_input_fits():
    blocks = [_block(i, f"line {i}") for i in range(1, 6)]
    batches = chunk_srt_blocks(blocks)
    assert len(batches) == 1
    assert batches[0].index == 0
    assert [b.index for b in batches[0].blocks] == [1, 2, 3, 4, 5]
    assert batches[0].approximate_chars == sum(len("line " + str(i)) for i in range(1, 6))


def test_chunk_srt_blocks_splits_on_max_blocks():
    blocks = [_block(i, f"line {i}") for i in range(1, 8)]
    batches = chunk_srt_blocks(blocks, max_blocks=3, max_chars=10_000)
    assert [len(b.blocks) for b in batches] == [3, 3, 1]
    assert [b.index for b in batches] == [0, 1, 2]
    # Order preservation across batches.
    flat = [b.index for batch in batches for b in batch.blocks]
    assert flat == [1, 2, 3, 4, 5, 6, 7]


def test_chunk_srt_blocks_splits_on_max_chars():
    # Each block is 10 chars after strip; cap at 25 → batches of 2, 2, 1.
    blocks = [_block(i, "abcdefghij") for i in range(1, 6)]
    batches = chunk_srt_blocks(blocks, max_blocks=100, max_chars=25)
    assert [len(b.blocks) for b in batches] == [2, 2, 1]
    # The "current batch is empty" guard must NOT cause a leading empty
    # batch — all batches are non-empty and contiguous.
    assert all(len(b.blocks) > 0 for b in batches)
    assert [b.index for b in batches] == [0, 1, 2]


def test_chunk_srt_blocks_preserves_original_indices_in_order():
    blocks = [_block(i, "x") for i in (1, 3, 5, 7, 9, 11)]
    batches = chunk_srt_blocks(blocks, max_blocks=2, max_chars=10_000)
    flat = [b.index for batch in batches for b in batch.blocks]
    assert flat == [1, 3, 5, 7, 9, 11]
    assert all(isinstance(b, TranslationBatch) for b in batches)


def test_chunk_srt_blocks_oversized_single_block_is_emitted_alone():
    # A single block whose stripped text length exceeds max_chars.
    big = "x" * 200
    blocks = [_block(1, "tiny"), _block(2, big), _block(3, "small")]
    batches = chunk_srt_blocks(blocks, max_blocks=10, max_chars=50)
    # The oversized block must NOT be silently dropped; it gets its own batch.
    flat = [b.index for batch in batches for b in batch.blocks]
    assert flat == [1, 2, 3]
    middle = next(b for b in batches if any(bk.index == 2 for bk in b.blocks))
    assert middle.approximate_chars >= 200
    assert middle.approximate_chars > 50  # documented overflow


def test_chunk_srt_blocks_default_knobs_align_with_tts_batch_size():
    # Phase 1C deliberately mirrors defaults.tts_batch_size = 30 so the
    # two batching surfaces feel consistent to operators reading
    # config.yaml.
    assert DEFAULT_TRANSLATION_BATCH_BLOCKS == 30
    assert DEFAULT_TRANSLATION_BATCH_CHARS == 4000
    # Sanity: feeding 60 short blocks with defaults produces exactly 2 batches.
    blocks = [_block(i, "hi") for i in range(1, 61)]
    batches = chunk_srt_blocks(blocks)
    assert [len(b.blocks) for b in batches] == [30, 30]


# ---------------------------------------------------------------------------
# verify_translated_blocks
# ---------------------------------------------------------------------------


def _src(n: int) -> list[SubtitleBlock]:
    return [_block(i, f"src {i}") for i in range(1, n + 1)]


def test_verify_translated_blocks_ok_on_matching_count():
    src = _src(3)
    v = verify_translated_blocks(src, ["你好 1", "你好 2", "你好 3"])
    assert isinstance(v, TranslationVerification)
    assert v.ok is True
    assert v.block_count_match is True
    assert v.indices_preserved is True
    assert v.timing_preserved is True
    assert v.issues == []


def test_verify_translated_blocks_detects_count_mismatch():
    src = _src(3)
    v = verify_translated_blocks(src, ["only one"])
    assert v.ok is False
    assert v.block_count_match is False
    assert v.indices_preserved is False
    assert any("block_count_mismatch" in issue for issue in v.issues)


def test_verify_translated_blocks_detects_duplicate_source_indices():
    # Two source blocks share index=1 — corruption that would silently
    # misalign TTS clip timing if not caught.
    src = [_block(1, "a"), _block(1, "b"), _block(2, "c")]
    v = verify_translated_blocks(src, ["x", "y", "z"])
    assert v.ok is False
    assert v.indices_preserved is False
    assert any("duplicate_source_indices" in issue for issue in v.issues)


def test_verify_translated_blocks_detects_invalid_source_timing():
    # A source block with no "-->" in its timing line is structurally
    # broken and would corrupt the rendered SRT.
    src = [
        _block(1, "a"),
        SubtitleBlock(index=2, timing="not-a-timing-line", text="b"),
        _block(3, "c"),
    ]
    v = verify_translated_blocks(src, ["x", "y", "z"])
    assert v.ok is False
    assert v.timing_preserved is False
    assert any("invalid_source_timing" in issue for issue in v.issues)
    # The structured fields must be independently settable so callers
    # can act on a single failure mode without parsing the issue list.
    assert v.block_count_match is True
    assert v.indices_preserved is True


def test_verify_translated_blocks_combines_independent_failures():
    # All three failure modes at once: count mismatch + duplicates + bad timing.
    src = [
        _block(1, "a"),
        SubtitleBlock(index=1, timing="", text="b"),
    ]
    v = verify_translated_blocks(src, ["only one"])
    assert v.ok is False
    assert v.block_count_match is False
    assert v.indices_preserved is False
    assert v.timing_preserved is False
    # Issues list should mention each failure mode at least once.
    joined = " | ".join(v.issues)
    assert "block_count_mismatch" in joined
    assert "duplicate_source_indices" in joined
    assert "invalid_source_timing" in joined


def test_verify_translated_blocks_issues_are_list_not_string():
    src = _src(2)
    v = verify_translated_blocks(src, ["x"])
    assert isinstance(v.issues, list)
    # Issues must be a list of strings, not a single concatenated blob.
    assert all(isinstance(item, str) for item in v.issues)
    assert len(v.issues) >= 1
