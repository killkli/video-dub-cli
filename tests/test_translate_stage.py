from __future__ import annotations

from pathlib import Path

from dub.config import DubConfig
from dub.stages.translate import TranslateStage


def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    (project_dir / "03_asr").mkdir(parents=True)
    (project_dir / "03_asr" / "video.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nHow are you?\n",
        encoding="utf-8",
    )
    return project_dir


def test_translate_stage_calls_committed_gemini_route(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)
    seen = {}

    def fake_translate_srt_file(*, src_srt, dst_srt, source_lang, target_lang, cfg):
        seen["src_srt"] = src_srt
        seen["dst_srt"] = dst_srt
        seen["source_lang"] = source_lang
        seen["target_lang"] = target_lang
        seen["provider"] = cfg.provider
        dst_srt.parent.mkdir(parents=True, exist_ok=True)
        dst_srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n你好\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n你好吗？\n",
            encoding="utf-8",
        )
        return dst_srt

    monkeypatch.setattr("dub.stages.translate.translate_srt_file", fake_translate_srt_file)

    cfg = DubConfig()
    state = TranslateStage().run(proj, cfg)

    assert state.status == "done"
    assert seen["src_srt"] == proj / "03_asr" / "video.srt"
    assert seen["dst_srt"] == proj / "05_translated_srt" / "video.zhtw.srt"
    assert seen["source_lang"] == cfg.defaults.source_lang
    assert seen["target_lang"] == cfg.defaults.target_lang
    assert seen["provider"] == cfg.translation.provider
    assert (proj / "05_translated_srt" / "video.zhtw.srt").exists()


def test_translate_stage_fails_when_asr_srt_missing(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir(parents=True)

    state = TranslateStage().run(proj, DubConfig())

    assert state.status == "failed"
    assert state.error is not None
    assert "Missing ASR SRT" in state.error


def test_translate_stage_surfaces_translation_error(tmp_path, monkeypatch):
    proj = _make_project(tmp_path)

    def fake_translate_srt_file(*, src_srt, dst_srt, source_lang, target_lang, cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr("dub.stages.translate.translate_srt_file", fake_translate_srt_file)

    state = TranslateStage().run(proj, DubConfig())

    assert state.status == "failed"
    assert state.error == "boom"


def test_translate_stage_is_done_requires_nontrivial_output(tmp_path):
    proj = tmp_path / "proj"
    (proj / "05_translated_srt").mkdir(parents=True)
    srt = proj / "05_translated_srt" / "video.zhtw.srt"
    srt.write_text("short", encoding="utf-8")

    stage = TranslateStage()
    assert stage.is_done(proj) is False

    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n你好世界\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n第二行翻譯\n",
        encoding="utf-8",
    )
    assert stage.is_done(proj) is True
