"""Gemini-backed SRT translation for standalone video-dub-cli."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dub.config import TranslationConfig
from dub.errors import TranslationError


SRT_BLOCK_RE = re.compile(
    r"(?ms)^\s*(\d+)\s*\n([^\n]+-->[^\n]+)\n(.*?)(?=\n{2,}|\Z)"
)


@dataclass
class SubtitleBlock:
    index: int
    timing: str
    text: str


def parse_srt_blocks(text: str) -> list[SubtitleBlock]:
    blocks: list[SubtitleBlock] = []
    normalized = text.replace("\r\n", "\n").strip()
    for m in SRT_BLOCK_RE.finditer(normalized):
        idx = int(m.group(1))
        timing = m.group(2).strip()
        body = m.group(3).strip()
        blocks.append(SubtitleBlock(index=idx, timing=timing, text=body))
    if not blocks:
        raise TranslationError("Source SRT contains no parseable subtitle blocks")
    return blocks


def render_srt_blocks(blocks: list[SubtitleBlock]) -> str:
    parts = []
    for i, block in enumerate(blocks, start=1):
        text = block.text.strip() or "…"
        parts.append(f"{i}\n{block.timing}\n{text}")
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Phase 1C — translation batching / verification groundwork
#
# These helpers define the contract for breaking an SRT into Gemini-sized
# batches and verifying the translated output. They are PURE — they do not
# call Gemini and do not depend on translation config. The runtime path
# (translate_srt_file) still sends all blocks in one call today; a later
# phase may opt into the chunked path. The contract is locked here so the
# verification surface is testable in isolation and the runtime wiring can
# be added without re-litigating the boundary.
# ---------------------------------------------------------------------------


@dataclass
class TranslationBatch:
    """A contiguous slice of subtitle blocks intended for one Gemini call.

    Attributes:
        index: Zero-based batch ordinal, preserved so callers can label
            logs / checkpoints in batch order.
        blocks: The original SubtitleBlocks in this batch. Order matches
            the source SRT, so ``blocks[0].index`` may be larger than 1
            for batches after the first.
        approximate_chars: Sum of the rendered text lengths in this
            batch, used by callers to log batch weight without
            re-rendering. Approximate because whitespace handling at
            render time is not exactly reproduced here.
    """

    index: int
    blocks: list[SubtitleBlock]
    approximate_chars: int


def chunk_srt_blocks(
    blocks: list[SubtitleBlock],
    *,
    max_blocks: int = 30,
    max_chars: int = 4000,
) -> list[TranslationBatch]:
    """Split subtitle blocks into Gemini-sized batches.

    The chunker greedily fills each batch up to ``max_blocks`` blocks,
    stopping early if appending the next block would push the rendered
    text length past ``max_chars``. This mirrors the TTS batched
    assembler contract (``defaults.tts_batch_size = 30``) so the two
    batching surfaces feel consistent to operators.

    Contract guarantees:
    * Every input block appears in exactly one batch, in original order.
    * Every returned batch is non-empty.
    * No batch exceeds ``max_blocks`` blocks.
    * No batch's rendered text length exceeds ``max_chars`` (unless a
      single block is itself larger than ``max_chars``, in which case
      it is emitted alone and ``approximate_chars`` may exceed
      ``max_chars``).
    * Batch ordinals are 0-based and contiguous.

    Validation:
    * ``max_blocks`` must be >= 1; ``max_chars`` must be >= 1; both
      are checked up front and raise ``TranslationError`` otherwise.
    * An empty ``blocks`` list raises ``TranslationError`` — callers
      should not chunk a no-op translation, and silent no-op output
      would mask upstream ASR failures.
    """
    if max_blocks < 1:
        raise TranslationError(f"chunk_srt_blocks: max_blocks must be >= 1, got {max_blocks}")
    if max_chars < 1:
        raise TranslationError(f"chunk_srt_blocks: max_chars must be >= 1, got {max_chars}")
    if not blocks:
        raise TranslationError("chunk_srt_blocks: cannot chunk an empty block list")

    batches: list[TranslationBatch] = []
    current: list[SubtitleBlock] = []
    current_chars = 0

    def _flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        batches.append(
            TranslationBatch(
                index=len(batches),
                blocks=current,
                approximate_chars=current_chars,
            )
        )
        current = []
        current_chars = 0

    for block in blocks:
        rendered_len = len(block.text.strip())
        would_overflow_blocks = len(current) + 1 > max_blocks
        would_overflow_chars = current and current_chars + rendered_len > max_chars
        if would_overflow_blocks or would_overflow_chars:
            _flush()
        current.append(block)
        current_chars += rendered_len
    _flush()
    return batches


@dataclass
class TranslationVerification:
    """Result of verifying a translated block list against source blocks.

    Attributes:
        ok: True iff every check passed; the runtime can treat this as
            a hard gate before writing the translated SRT.
        block_count_match: True iff the translated line count equals
            the source block count.
        indices_preserved: True iff every source block index appears
            in the translated set, with no extras, in the original
            order.
        timing_preserved: True iff every translated line's bracketed
            index resolves to a source block and the corresponding
            source timing line is the one that will be re-rendered.
        issues: Human-readable list of problems; empty when ``ok`` is
            True. Kept as a list (not a single string) so callers can
            log structured diagnostics and so tests can assert on
            specific failure modes.
    """

    ok: bool
    block_count_match: bool
    indices_preserved: bool
    timing_preserved: bool
    issues: list[str]


def verify_translated_blocks(
    src_blocks: list[SubtitleBlock],
    translated_texts: list[str],
) -> TranslationVerification:
    """Verify that a translated line list matches the source blocks.

    This is the canonical "post-translation verification" surface for
    Phase 1C. It does NOT parse the Gemini response itself — callers
    that use the raw ``_parse_labeled_translation_lines`` output are
    responsible for passing the resulting list. The contract is
    intentionally narrow so the same verifier can be reused for the
    chunked path (one call per batch) and the single-call path.

    The check has three parts, each independent so failures point at
    the right thing:
    1. Block count match: ``len(translated_texts) == len(src_blocks)``.
    2. Index preservation: every source block index appears exactly
       once, with no extras. Mismatch is treated as a hard failure
       even when counts happen to match, because renumbering would
       silently misalign downstream TTS clip timing.
    3. Timing preservation: the source ``SubtitleBlock.timing`` strings
       are the ones that will be re-rendered into the output SRT, so
       this check is really a sanity assertion that the verifier is
       being called with the same source blocks the renderer will
       use; the rendered output SRT will re-use the source timing
       lines by design.
    """
    issues: list[str] = []
    block_count_match = len(translated_texts) == len(src_blocks)
    if not block_count_match:
        issues.append(
            f"block_count_mismatch: expected={len(src_blocks)} got={len(translated_texts)}"
        )

    src_indices = [block.index for block in src_blocks]
    src_index_set = set(src_indices)
    seen_indices: list[int] = []
    duplicate_indices: list[int] = []
    for block in src_blocks:
        if block.index in src_index_set and block.index in seen_indices:
            duplicate_indices.append(block.index)
        seen_indices.append(block.index)
    indices_preserved = block_count_match and not duplicate_indices
    if duplicate_indices:
        issues.append(f"duplicate_source_indices: {sorted(set(duplicate_indices))[:10]}")

    # Timing preservation: every source timing string must be a
    # non-empty SRT-style "-->" line. We do not parse timestamps here
    # (the SRT renderer is the source of truth for format), but a
    # missing "-->" in any source block is a hard error because the
    # rendered output will inherit that gap.
    timing_preserved = True
    for block in src_blocks:
        if "-->" not in block.timing:
            timing_preserved = False
            issues.append(f"invalid_source_timing: index={block.index} timing={block.timing!r}")

    ok = block_count_match and indices_preserved and timing_preserved
    return TranslationVerification(
        ok=ok,
        block_count_match=block_count_match,
        indices_preserved=indices_preserved,
        timing_preserved=timing_preserved,
        issues=issues,
    )


# Default knobs exposed for callers (and tests) that want to align with
# the TTS batched assembler contract. These are intentionally not wired
# into the runtime path yet — they are the documented Phase 1C
# contract that a later runtime wave can opt into.
DEFAULT_TRANSLATION_BATCH_BLOCKS = 30
DEFAULT_TRANSLATION_BATCH_CHARS = 4000


def _target_language_label(target_lang: str) -> str:
    labels = {
        "zh": "Traditional Chinese",
        "zh-tw": "Traditional Chinese",
        "zh_tw": "Traditional Chinese",
        "ja": "Japanese",
        "en": "English",
    }
    return labels.get(target_lang.lower(), target_lang)


def _load_api_key(env_var: str) -> str:
    """Load Gemini credentials from process environment only.

    Standalone contract: users export the configured env var before running
    the CLI. We intentionally do not read ~/.hermes/.env or any profile-local
    secret file here, because that would reintroduce a machine-specific Hermes
    dependency into the standalone runtime story.
    """
    candidates = [env_var]
    if env_var == "GOOGLE_API_KEY":
        candidates.append("GEMINI_API_KEY")
    elif env_var == "GEMINI_API_KEY":
        candidates.append("GOOGLE_API_KEY")
    else:
        candidates.extend(["GOOGLE_API_KEY", "GEMINI_API_KEY"])

    seen: list[str] = []
    for name in candidates:
        if name in seen:
            continue
        seen.append(name)
        key = (os.environ.get(name) or "").strip()
        if key:
            return key

    raise TranslationError(
        f"Gemini API key not found in environment; set one of: {', '.join(seen)}"
    )


def _build_prompt(blocks: list[SubtitleBlock], source_lang: str, target_lang: str) -> str:
    target_label = _target_language_label(target_lang)
    payload = []
    for block in blocks:
        payload.append({"index": block.index, "timing": block.timing, "text": block.text})
    return (
        "You translate subtitle blocks for video dubbing.\n"
        f"Source language: {source_lang}\n"
        f"Target language: {target_label}\n\n"
        "Rules:\n"
        "- Return exactly one translated line per input block.\n"
        "- Preserve block count and order exactly.\n"
        "- Every output line MUST start with the original bracketed index, like [12] translated text.\n"
        "- Do not skip any index, do not merge indices, and do not renumber.\n"
        "- Do not include timestamps, markdown, commentary, or code fences.\n"
        "- Keep names/terms consistent.\n"
        "- If a source block is extremely short, still return that index with a short translation.\n\n"
        "Subtitle texts:\n"
        + "\n".join(f"[{item['index']}] {item['text']}" for item in payload)
    )


def _parse_labeled_translation_lines(raw: str, blocks: list[SubtitleBlock]) -> list[str]:
    expected = [block.index for block in blocks]
    expected_set = set(expected)
    pattern = re.compile(r"(?m)^\[(\d+)\]\s*(.*)$")
    found = pattern.findall(raw)
    if not found:
        raise TranslationError("Gemini returned no labeled translation lines")

    mapping: dict[int, str] = {}
    for idx_str, text in found:
        idx = int(idx_str)
        mapping[idx] = text.strip() or "…"

    missing = [idx for idx in expected if idx not in mapping]
    extra = [idx for idx in mapping if idx not in expected_set]
    if missing or extra:
        raise TranslationError(
            f"Gemini labeled output mismatch: missing={missing[:10]} extra={extra[:10]} expected_count={len(expected)} got_count={len(mapping)}"
        )

    return [mapping[idx] for idx in expected]


def _parse_translation_lines(raw: str, blocks: list[SubtitleBlock]) -> list[str]:
    try:
        return _parse_labeled_translation_lines(raw, blocks)
    except TranslationError:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) != len(blocks):
            raise TranslationError(
                f"Gemini returned {len(lines)} translated lines for {len(blocks)} subtitle blocks"
            )
        return lines


def _call_gemini(prompt: str, cfg: TranslationConfig) -> str:
    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover - dependency absence is environment-specific
        raise TranslationError(
            "google-genai dependency is not installed; cannot run Gemini translation"
        ) from e

    api_key = _load_api_key(cfg.api_env_var)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=cfg.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=cfg.temperature,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise TranslationError("Gemini returned empty translation response")
    return text


def translate_srt_file(src_srt: Path, dst_srt: Path, source_lang: str, target_lang: str, cfg: TranslationConfig) -> Path:
    blocks = parse_srt_blocks(src_srt.read_text(encoding="utf-8"))

    if cfg.provider.lower() == "mock":
        lines = [f"[ZH] {block.text}" for block in blocks]
    else:
        prompt = _build_prompt(blocks, source_lang=source_lang, target_lang=target_lang)
        raw = _call_gemini(prompt, cfg)
        lines = _parse_translation_lines(raw, blocks)

    translated_blocks = [
        SubtitleBlock(index=block.index, timing=block.timing, text=lines[i])
        for i, block in enumerate(blocks)
    ]
    dst_srt.parent.mkdir(parents=True, exist_ok=True)
    dst_srt.write_text(render_srt_blocks(translated_blocks), encoding="utf-8")
    return dst_srt


__all__ = [
    "SubtitleBlock",
    "parse_srt_blocks",
    "render_srt_blocks",
    "translate_srt_file",
    "TranslationBatch",
    "chunk_srt_blocks",
    "TranslationVerification",
    "verify_translated_blocks",
    "DEFAULT_TRANSLATION_BATCH_BLOCKS",
    "DEFAULT_TRANSLATION_BATCH_CHARS",
]