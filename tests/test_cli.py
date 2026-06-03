import pytest
from click.testing import CliRunner
from dub.cli import main
from dub.state import load_state
from dub.state import save_state


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


def test_dub_bootstrap_exits_zero(runner):
    result = runner.invoke(main, ["bootstrap"])
    assert result.exit_code == 0
    assert "uv sync" in result.output


def test_dub_doctor_reports_missing_prereqs(runner, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: nonexistent-qwen-bin\n"
        "  omnivoice_python: nonexistent-python-bin\n"
        "  translation_skill: /tmp/trans.py\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["doctor", "--config", str(cfg)])
    assert result.exit_code != 0
    assert "repo_pipeline_scripts: OK" in result.output
    assert "tts_backends:" in result.output
    assert "omnivoice: BLOCKED" in result.output
    assert "doctor found missing prerequisites" in result.output


def _make_validate_project(tmp_path, *, translate_mode="delegate", translate_stage_status="done"):
    project_dir = tmp_path / "proj"
    for rel in [
        "01_raw_video",
        "02_stems",
        "03_asr",
        "04_ref_audio",
        "05_translate",
        "05_translated_srt",
        "06_tts_wav",
        "07_final",
        ".dub",
    ]:
        (project_dir / rel).mkdir(parents=True, exist_ok=True)

    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")
    (project_dir / "03_asr" / "video.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
        encoding="utf-8",
    )

    state = {
        "project_id": project_dir.name,
        "input": {
            "translate_mode": translate_mode,
            "translated_srt": "/tmp/external.zhtw.srt" if translate_mode == "use-existing" else None,
        },
        "stages": {
            "01_stems": {"status": "done", "attempts": 1, "artifacts": [], "output_dir": "02_stems", "error": None},
            "02_asr": {"status": "done", "attempts": 1, "artifacts": ["video.srt"], "output_dir": "03_asr", "error": None},
            "03_ref_audio": {"status": "done", "attempts": 1, "artifacts": [], "output_dir": "04_ref_audio", "error": None},
            "04_translate": {"status": translate_stage_status, "attempts": 1, "artifacts": ["video.zhtw.srt"] if translate_stage_status == "done" else [], "output_dir": "05_translated_srt", "error": None},
            "05_tts": {"status": "pending", "attempts": 0, "artifacts": [], "output_dir": None, "error": None},
            "06_assemble": {"status": "pending", "attempts": 0, "artifacts": [], "output_dir": None, "error": None},
        },
    }
    save_state(project_dir, state)
    return project_dir


def test_dub_validate_fails_when_translated_srt_required_but_missing(runner, tmp_path):
    project_dir = _make_validate_project(tmp_path, translate_mode="delegate", translate_stage_status="done")

    result = runner.invoke(main, ["validate", "--project-dir", str(project_dir)])

    assert result.exit_code != 0
    assert "translated subtitle required but missing" in result.output
    assert "mode=delegate" in result.output


def test_dub_validate_allows_missing_translated_srt_when_translate_stage_skipped(runner, tmp_path):
    project_dir = _make_validate_project(tmp_path, translate_mode="skip", translate_stage_status="skipped")

    result = runner.invoke(main, ["validate", "--project-dir", str(project_dir)])

    assert result.exit_code == 0
    assert "validate ok:" in result.output
    assert "mode=skip" in result.output


def test_dub_validate_ok_when_use_existing_translated_srt_present(runner, tmp_path):
    project_dir = _make_validate_project(tmp_path, translate_mode="use-existing", translate_stage_status="done")
    translated = project_dir / "05_translated_srt" / "video.zhtw.srt"
    translated.write_text("1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8")

    result = runner.invoke(main, ["validate", "--project-dir", str(project_dir)])

    assert result.exit_code == 0
    assert "validate ok:" in result.output
    assert "mode=use-existing" in result.output


def test_dub_run_use_existing_requires_translated_srt(runner, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        [
            "run", str(video),
            "--project-dir", str(tmp_path / "proj"),
            "--config", str(cfg),
            "--translate-mode", "use-existing",
        ],
    )

    assert result.exit_code != 0
    assert "requires --translated-srt" in result.output


def test_dub_run_skip_requires_existing_project_translated_srt(runner, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        [
            "run", str(video),
            "--project-dir", str(tmp_path / "proj"),
            "--config", str(cfg),
            "--translate-mode", "skip",
        ],
    )

    assert result.exit_code != 0
    assert "translate-mode=skip requires an existing translated subtitle" in result.output


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
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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


def test_dub_resume_restores_source_lang_from_state(runner, tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")
    save_state(project_dir, {
        "project_id": project_dir.name,
        "input": {
            "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
            "video_sha256": "abc",
            "duration_sec": 1.23,
            "source_lang": "ja",
            "target_lang": "zh",
            "translate_mode": "delegate",
            "translated_srt": None,
        },
        "stages": {},
    })

    seen = {}

    def fake_run_pipeline(project_dir_arg, cfg, yes=False):
        seen["source_lang"] = cfg.defaults.source_lang
        seen["target_lang"] = cfg.defaults.target_lang
        seen["translate_mode"] = cfg.translation.mode
        return {"ok": True}

    monkeypatch.setattr("dub.cli.run_pipeline", fake_run_pipeline)

    result = runner.invoke(main, ["resume", "--project-dir", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert seen["source_lang"] == "ja"
    assert seen["target_lang"] == "zh"
    assert seen["translate_mode"] == "delegate"


def test_dub_run_prints_preflight_route_summary(runner, tmp_path, monkeypatch):
    """P4 Contract 1: dub run prints a single preflight: line with src/tgt/project/mode/route."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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
            "--source-lang", "ja",
            "--target-lang", "zh",
            "--translate-mode", "delegate",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output

    preflight_lines = [
        line for line in result.output.splitlines()
        if line.startswith("preflight:")
    ]
    assert len(preflight_lines) == 1, result.output
    preflight = preflight_lines[0]
    assert f"src=ja" in preflight
    assert f"tgt=zh" in preflight
    assert f"project={project_dir}" in preflight
    assert f"mode=delegate" in preflight
    assert "route=" in preflight
    assert "translate=delegate" in preflight


def test_dub_resume_restores_use_existing_route_from_state(runner, tmp_path, monkeypatch):
    """P4 Contract 1: dub resume re-applies state-derived route (use-existing mode + external srt) on a fresh invocation."""
    project_dir = tmp_path / "proj"
    (project_dir / "01_raw_video").mkdir(parents=True)
    (project_dir / ".dub").mkdir(parents=True)
    (project_dir / "01_raw_video" / "video.mp4").write_bytes(b"fake")
    external_srt = tmp_path / "external.zhtw.srt"
    external_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8")

    save_state(project_dir, {
        "project_id": project_dir.name,
        "input": {
            "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
            "video_sha256": "abc",
            "duration_sec": 1.23,
            "source_lang": "en",
            "target_lang": "zh",
            "translate_mode": "use-existing",
            "translated_srt": str(external_srt),
        },
        "stages": {},
    })

    seen = {}

    def fake_run_pipeline(project_dir_arg, cfg, yes=False):
        seen["source_lang"] = cfg.defaults.source_lang
        seen["target_lang"] = cfg.defaults.target_lang
        seen["translate_mode"] = cfg.translation.mode
        seen["translated_srt"] = str(cfg.translation.translated_srt) if cfg.translation.translated_srt else None
        return {"ok": True}

    monkeypatch.setattr("dub.cli.run_pipeline", fake_run_pipeline)

    result = runner.invoke(main, ["resume", "--project-dir", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert seen["source_lang"] == "en"
    assert seen["target_lang"] == "zh"
    assert seen["translate_mode"] == "use-existing"
    assert seen["translated_srt"] == str(external_srt)


def test_dub_run_use_existing_fails_with_nonexistent_translated_srt_path(runner, tmp_path):
    """FR-2 from QA matrix: --translated-srt pointing to a non-existent file must fail fast."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        [
            "run", str(video),
            "--project-dir", str(tmp_path / "proj"),
            "--config", str(cfg),
            "--translate-mode", "use-existing",
            "--translated-srt", "/nonexistent/path/missing.srt",
        ],
    )

    assert result.exit_code != 0
    assert "translated SRT not found: /nonexistent/path/missing.srt" in result.output


def test_dub_run_skip_succeeds_when_project_already_has_translated_srt(runner, tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    (project_dir / "05_translated_srt").mkdir(parents=True)
    (project_dir / "05_translated_srt" / "video.zhtw.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n哈囉\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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
            "--translate-mode", "skip",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output


def test_dub_run_accepts_video_already_at_project_canonical_path(runner, tmp_path, monkeypatch):
    project_dir = tmp_path / "proj"
    canonical_video = project_dir / "01_raw_video" / "video.mp4"
    canonical_video.parent.mkdir(parents=True)
    canonical_video.write_bytes(b"fake")

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("dub.cli.project_input_info", lambda _: {
        "video_path": str(canonical_video),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *args, **kwargs: {"ok": True})

    result = runner.invoke(
        main,
        [
            "run", str(canonical_video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--translate-mode", "delegate",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert canonical_video.exists()


def test_dub_run_prints_delegate_preflight_summary(runner, tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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
            "--source-lang", "en",
            "--target-lang", "zh",
            "--translate-mode", "delegate",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "preflight:" in result.output
    assert "mode=delegate" in result.output
    assert "route=translate=delegate" in result.output


def test_dub_run_prints_use_existing_preflight_summary(runner, tmp_path, monkeypatch):
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
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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
    assert "mode=use-existing" in result.output
    assert f"external_srt={translated}" in result.output


def test_dub_run_prints_skip_preflight_summary(runner, tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    (project_dir / "05_translated_srt").mkdir(parents=True)
    existing = project_dir / "05_translated_srt" / "video.zhtw.srt"
    existing.write_text("1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
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
            "--translate-mode", "skip",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "mode=skip" in result.output
    assert f"existing_project_srt={existing}" in result.output
