import pytest
from click.testing import CliRunner
from dub.cli import main
from dub.state import load_state


@pytest.fixture
def runner():
    return CliRunner()


def test_dub_help_exits_zero(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "video-dub-cli" in result.output


def test_dub_run_help_exits_zero(runner):
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "VIDEO is the source mp4 path" in result.output


def test_dub_run_nonexistent_exits_2(runner):
    result = runner.invoke(main, ["run", "/nonexistent.mp4"])
    assert result.exit_code == 2


def test_dub_resume_exits_zero(runner):
    result = runner.invoke(main, ["resume", "--project-dir", "/tmp"])
    assert result.exit_code == 0


def test_dub_resume_accepts_config_flag(runner, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("paths:\n  qwenasr_cli: /bin/true\n", encoding="utf-8")
    result = runner.invoke(main, ["resume", "--project-dir", "/tmp", "--config", str(cfg)])
    assert result.exit_code == 0


def test_dub_status_exits_zero(runner):
    result = runner.invoke(main, ["status", "--project-dir", "/tmp"])
    assert result.exit_code == 0


def test_dub_clean_exits_zero(runner):
    result = runner.invoke(main, ["clean", "--project-dir", "/tmp", "--stage", "5"])
    assert result.exit_code == 0


def test_dub_validate_exits_zero(runner):
    result = runner.invoke(main, ["validate", "--project-dir", "/tmp"])
    assert result.exit_code == 0


def test_dub_run_persists_translate_mode_and_translated_srt(runner, tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    translated = tmp_path / "translated.srt"
    translated.write_text("1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("dub.cli.project_input_info", lambda _: {
        "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *args, **kwargs: {"ok": True})

    result = runner.invoke(
        main,
        [
            "run", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--translate-mode", "use-existing",
            "--translated-srt", str(translated),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    state = load_state(project_dir)
    assert state.input["translate_mode"] == "use-existing"
    assert state.input["translated_srt"] == str(translated)