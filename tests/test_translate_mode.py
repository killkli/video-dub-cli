from __future__ import annotations

from pathlib import Path

from dub.config import DubConfig, PathsConfig
from dub.stages.translate import TranslateStage


def _cfg() -> DubConfig:
    return DubConfig(
        paths=PathsConfig(
            qwenasr_cli=Path("/bin/true"),
            omnivoice_python=Path("/bin/true"),
            skills_dir=Path("/tmp"),
            translation_skill=Path("/bin/true"),
        )
    )


def _proj(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "03_asr").mkdir(parents=True)
    (proj / "05_translate").mkdir(parents=True)
    (proj / "05_translated_srt").mkdir(parents=True)
    (proj / "03_asr" / "video.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        encoding="utf-8",
    )
    return proj


def test_translate_stage_use_existing_copies_both_aliases(tmp_path: Path) -> None:
    proj = _proj(tmp_path)
    existing = tmp_path / "existing.zhtw.srt"
    existing.write_text("1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8")
    cfg = _cfg()
    cfg.translation.mode = "use-existing"
    cfg.translation.translated_srt = existing

    st = TranslateStage().run(proj, cfg)

    assert st.status == "done"
    assert (proj / "05_translate" / "video.zhtw.srt").read_text(encoding="utf-8") == existing.read_text(encoding="utf-8")
    assert (proj / "05_translated_srt" / "video.zhtw.srt").read_text(encoding="utf-8") == existing.read_text(encoding="utf-8")


def test_translate_stage_use_existing_requires_path(tmp_path: Path) -> None:
    proj = _proj(tmp_path)
    cfg = _cfg()
    cfg.translation.mode = "use-existing"

    st = TranslateStage().run(proj, cfg)

    assert st.status == "failed"
    assert "requires --translated-srt" in (st.error or "")


def test_translate_stage_skip_returns_skipped(tmp_path: Path) -> None:
    proj = _proj(tmp_path)
    cfg = _cfg()
    cfg.translation.mode = "skip"

    st = TranslateStage().run(proj, cfg)

    assert st.status == "skipped"
    assert not (proj / "05_translated_srt" / "video.zhtw.srt").exists()
