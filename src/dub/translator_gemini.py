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
    key = (os.environ.get(env_var) or "").strip()
    if key:
        return key

    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text(errors="ignore").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == env_var:
                return v.strip().strip('"').strip("'")

    fallbacks = ["GOOGLE_API_KEY", "GEMINI_API_KEY"] if env_var == "GOOGLE_API_KEY" else ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    for fb in fallbacks:
        key = (os.environ.get(fb) or "").strip()
        if key:
            return key
        if env_path.exists():
            for line in env_path.read_text(errors="ignore").splitlines():
                if not line or line.lstrip().startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == fb:
                    return v.strip().strip('"').strip("'")
    raise TranslationError(f"Gemini API key not found via {env_var}, GOOGLE_API_KEY, or GEMINI_API_KEY")


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
        "- Return exactly one translated text line per input block.\n"
        "- Preserve block count and order exactly.\n"
        "- Do not include numbering, timestamps, markdown, commentary, or code fences.\n"
        "- Keep names/terms consistent.\n"
        "- Output plain text lines separated by newline only.\n\n"
        "Subtitle texts:\n"
        + "\n".join(f"[{item['index']}] {item['text']}" for item in payload)
    )


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
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) != len(blocks):
            raise TranslationError(
                f"Gemini returned {len(lines)} translated lines for {len(blocks)} subtitle blocks"
            )

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