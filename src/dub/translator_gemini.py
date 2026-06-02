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
]