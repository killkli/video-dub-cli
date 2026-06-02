from __future__ import annotations

from pathlib import Path

from dub.config import TranslationConfig
from dub.translator_gemini import parse_srt_blocks, render_srt_blocks, translate_srt_file


def test_parse_and_render_srt_roundtrip():
    src = """1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n"""
    blocks = parse_srt_blocks(src)
    assert len(blocks) == 2
    assert blocks[0].text == "Hello"
    rendered = render_srt_blocks(blocks)
    assert "00:00:01,000 --> 00:00:02,000" in rendered
    assert "World" in rendered


def test_translate_srt_file_with_mocked_gemini(tmp_path: Path, monkeypatch):
    src = tmp_path / "video.srt"
    dst = tmp_path / "video.zhtw.srt"
    src.write_text(
        """1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nHow are you?\n""",
        encoding="utf-8",
    )

    monkeypatch.setattr("dub.translator_gemini._call_gemini", lambda prompt, cfg: "你好\n你好吗？")

    out = translate_srt_file(
        src_srt=src,
        dst_srt=dst,
        source_lang="en",
        target_lang="zh",
        cfg=TranslationConfig(),
    )
    assert out == dst
    text = dst.read_text(encoding="utf-8")
    assert "你好" in text
    assert "你好吗？" in text
    assert "00:00:01,000 --> 00:00:02,000" in text


def test_translate_srt_file_mock_provider_for_offline_qa(tmp_path: Path):
    src = tmp_path / "video.srt"
    dst = tmp_path / "video.zhtw.srt"
    src.write_text(
        """1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n""",
        encoding="utf-8",
    )

    out = translate_srt_file(
        src_srt=src,
        dst_srt=dst,
        source_lang="en",
        target_lang="zh",
        cfg=TranslationConfig(provider="mock"),
    )
    assert out == dst
    text = dst.read_text(encoding="utf-8")
    assert "[ZH] Hello" in text
    assert "[ZH] World" in text
