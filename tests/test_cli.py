from pathlib import Path

import pytest
import yaml
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


def test_dub_help_lists_one_shot_aliases(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "auto" in result.output
    assert "en2zh" in result.output
    assert "ja2zh" in result.output
    assert "run" in result.output


def test_dub_auto_help_exits_zero(runner):
    result = runner.invoke(main, ["auto", "--help"])
    assert result.exit_code == 0
    assert "one-command workflow" in result.output
    assert "--source-lang" in result.output


def test_dub_en2zh_help_exits_zero(runner):
    result = runner.invoke(main, ["en2zh", "--help"])
    assert result.exit_code == 0
    assert "English→Chinese" in result.output


def test_dub_ja2zh_help_exits_zero(runner):
    result = runner.invoke(main, ["ja2zh", "--help"])
    assert result.exit_code == 0
    assert "Japanese→Chinese" in result.output


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
    assert "repo-owned pipeline scripts live under vendor/pipeline_scripts" in result.output
    assert "the only required external secret is GOOGLE_API_KEY / GEMINI_API_KEY" in result.output
    assert "bootstrap-omnivoice" in result.output
    assert "bootstrap-voxcpm" in result.output


def test_dub_help_lists_bootstrap_omnivoice(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "bootstrap-omnivoice" in result.output
    assert "bootstrap-voxcpm" in result.output


def test_dub_bootstrap_omnivoice_requires_uv(runner, monkeypatch, tmp_path):
    monkeypatch.setattr("dub.cli.shutil.which", lambda name: None if name == "uv" else "/usr/bin/true")
    result = runner.invoke(
        main,
        ["bootstrap-omnivoice", "--venv-path", str(tmp_path / "ov-venv"), "--config", str(tmp_path / "cfg.yaml")],
    )
    assert result.exit_code != 0
    assert "requires `uv` on PATH" in result.output


def test_dub_bootstrap_omnivoice_updates_config(runner, monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, check, cwd):
        calls.append((cmd, check, cwd))
        if cmd[1] == "venv":
            venv_dir = Path(cmd[2])
            (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
            (venv_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        return None

    monkeypatch.setattr("dub.cli.shutil.which", lambda name: "/opt/homebrew/bin/uv" if name == "uv" else None)
    monkeypatch.setattr("dub.cli.subprocess.run", fake_run)

    cfg = tmp_path / "config.yaml"
    cfg.write_text("translation:\n  provider: gemini\n", encoding="utf-8")
    venv_dir = tmp_path / "ov-venv"
    result = runner.invoke(
        main,
        ["bootstrap-omnivoice", "--venv-path", str(venv_dir), "--config", str(cfg)],
    )
    assert result.exit_code == 0
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["paths"]["omnivoice_python"] == str((venv_dir / "bin" / "python").resolve())
    assert any(cmd[0][1] == "venv" for cmd in calls)
    assert any(cmd[0][1:4] == ["pip", "install", "--python"] for cmd in calls)
    assert "wrote paths.omnivoice_python" in result.output


def test_dub_bootstrap_voxcpm_updates_config(runner, monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, check, cwd):
        calls.append((cmd, check, cwd))
        if cmd[1] == "venv":
            venv_dir = Path(cmd[2])
            (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
            (venv_dir / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
        return None

    monkeypatch.setattr("dub.cli.shutil.which", lambda name: "/opt/homebrew/bin/uv" if name == "uv" else None)
    monkeypatch.setattr("dub.cli.subprocess.run", fake_run)

    cfg = tmp_path / "config.yaml"
    cfg.write_text("translation:\n  provider: gemini\n", encoding="utf-8")
    venv_dir = tmp_path / "vox-venv"
    result = runner.invoke(
        main,
        ["bootstrap-voxcpm", "--venv-path", str(venv_dir), "--config", str(cfg)],
    )
    assert result.exit_code == 0
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["paths"]["voxcpme_python"] == str((venv_dir / "bin" / "python").resolve())
    assert any(cmd[0][1] == "venv" for cmd in calls)
    assert any(cmd[0][1:4] == ["pip", "install", "--python"] for cmd in calls)
    assert "wrote paths.voxcpme_python" in result.output


def test_dub_doctor_reports_missing_prereqs(runner, tmp_path, monkeypatch):
    """Doctor must surface the actual gaps so the operator can act on them.

    Pre-Lane-M the assertion was: omnivoice must be BLOCKED. After Lane M:
      * the operator venv has omnivoice installed, so even a fake
        `paths.omnivoice_python` falls back to the dub venv's real omnivoice.
      * the operator venv has gradio_client, so voxcpme reads as READY too.
      * Gemini key is recovered from ~/.zshrc on the operator host, so the
        gemini gate goes from MISSING to OK without any config change.

    The contract we still want to enforce is: when there is a real
    missing prereq (here: an env var the operator has *not* exported
    anywhere), `dub doctor` must report it and exit non-zero. That is
    the operator-facing failure mode we are guarding.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: nonexistent-qwen-bin\n"
        "  omnivoice_python: nonexistent-python-bin\n"
        "  translation_skill: /tmp/trans.py\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "dub.cli._auto_recover_missing_secrets", lambda: []
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = runner.invoke(main, ["doctor", "--config", str(cfg)])
    assert result.exit_code != 0
    assert "repo_pipeline_scripts: OK" in result.output
    assert "tts_backends:" in result.output
    assert "gemini_api_key: MISSING" in result.output
    assert "doctor found missing prerequisites" in result.output


# ── Real-backend productization gates (Lane M) ───────────────────────────────


def test_dub_doctor_reports_real_backend_python_gates(runner, tmp_path):
    """`dub doctor` must list `py:google_genai` and `py:torchcodec` so the
    operator can confirm the real-backend runtime is wired without
    having to run a full pipeline first.
    """
    result = runner.invoke(main, ["doctor"])
    assert "py:google_genai:" in result.output
    assert "py:torchcodec:" in result.output


def test_auto_recover_missing_secrets_reads_zshrc(monkeypatch, tmp_path):
    """When GOOGLE_API_KEY is unset in env but exported in ~/.zshrc,
    `dub doctor` should auto-recover it and print a note. We redirect
    `Path.home()` via monkeypatching the module-level constant the helper
    uses.
    """
    import dub.cli as cli_mod
    from pathlib import Path

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".zshrc").write_text(
        'export GOOGLE_API_KEY="rc-secret-1234"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_mod.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    recovered = cli_mod._auto_recover_missing_secrets()
    assert "GOOGLE_API_KEY" in recovered
    import os
    assert os.environ["GOOGLE_API_KEY"] == "rc-secret-1234"


def test_auto_recover_does_not_override_existing(monkeypatch, tmp_path):
    import dub.cli as cli_mod

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".zshrc").write_text(
        'export GOOGLE_API_KEY="rc-secret-9999"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_mod.Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("GOOGLE_API_KEY", "env-wins")

    recovered = cli_mod._auto_recover_missing_secrets()
    assert recovered == []  # existing env value is preserved
    import os
    assert os.environ["GOOGLE_API_KEY"] == "env-wins"

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


def test_dub_en2zh_alias_sets_languages_and_completes(runner, tmp_path, monkeypatch):
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
            "en2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "preflight: src=en tgt=zh" in result.output
    state = load_state(project_dir)
    assert state.input["source_lang"] == "en"
    assert state.input["target_lang"] == "zh"


def test_dub_ja2zh_alias_sets_languages_and_completes(runner, tmp_path, monkeypatch):
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
            "ja2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "preflight: src=ja tgt=zh" in result.output
    state = load_state(project_dir)
    assert state.input["source_lang"] == "ja"
    assert state.input["target_lang"] == "zh"


def test_dub_auto_uses_explicit_source_lang_and_completes(runner, tmp_path, monkeypatch):
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
            "auto", str(video),
            "--source-lang", "ja",
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "preflight: src=ja tgt=zh" in result.output
    state = load_state(project_dir)
    assert state.input["source_lang"] == "ja"
    assert state.input["target_lang"] == "zh"


def test_dub_auto_uses_config_default_source_lang_when_flag_missing(runner, tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "defaults:\n"
        "  source_lang: ja\n"
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
            "auto", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "preflight: src=ja tgt=zh" in result.output
    state = load_state(project_dir)
    assert state.input["source_lang"] == "ja"


def test_dub_auto_rejects_unsupported_source_lang(runner, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "defaults:\n"
        "  source_lang: fr\n"
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )

    result = runner.invoke(main, ["auto", str(video), "--config", str(cfg)])

    assert result.exit_code != 0
    assert "dub auto requires source language en or ja" in result.output


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
    assert "provider=gemini" in preflight
    assert f"run complete: project={project_dir}" in result.output
    assert f"final={project_dir / '07_final' / 'video_dubbed_stem.mp4'}" in result.output
    assert f"next: dub status --project-dir {project_dir}" in result.output
    assert f"next: dub validate --project-dir {project_dir}" in result.output


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
    assert f"resume complete: project={project_dir}" in result.output
    assert f"final={project_dir / '07_final' / 'video_dubbed_stem.mp4'}" in result.output


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
    assert "route=translate=delegate provider=gemini" in result.output


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


# ── Auto-workflow contract (T3) ────────────────────────────────────────────


def test_dub_doctor_success_message_names_auto_workflow_lane(runner, monkeypatch):
    """AC-3: `dub doctor` must name the auto-workflow lane on success so
    a first-time operator knows what command the readiness gate applies to.

    We make every check report OK regardless of host state by monkeypatching
    the helpers `dub.cli.doctor` uses internally, then assert the lane-aware
    message and exit-zero.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])

    def _ok_which(_name):
        return (True, "/bin/fake")

    def _ok_path(_p):
        return (True, "/fake/path")

    def _ok_env(*_names):
        return (True, "GOOGLE_API_KEY")

    monkeypatch.setattr("dub.cli._which_status", _ok_which)
    monkeypatch.setattr("dub.cli._path_status", _ok_path)
    monkeypatch.setattr("dub.cli._env_status", _ok_env)

    def _ok_python_imports(_name):
        return ("ok", "/fake/import/path.py")

    monkeypatch.setattr("dub.tts_engines.diagnostics.python_imports", _ok_python_imports)

    ready = TtsReadiness(backend="fake", ready=True, detail="fake-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "builtin_backends", lambda: ("omnivoice", "voxcpme"))

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "ready for `dub auto`, `dub en2zh`, `dub ja2zh`" in result.output
    assert "run `dub auto <VIDEO>`" in result.output


def test_dub_doctor_fails_when_any_route_backend_is_blocked(runner, monkeypatch):
    """AUTO-S5: doctor must not claim both lanes are ready when one route's
    TTS backend is blocked. It should exit non-zero and print lane-aware
    ready/blocked status for the operator.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/path"))
    monkeypatch.setattr("dub.cli._env_status", lambda *_names: (True, "GOOGLE_API_KEY"))
    monkeypatch.setattr("dub.tts_engines.diagnostics.python_imports", lambda _name: ("ok", "/fake/import/path.py"))

    blocked_omni = TtsReadiness(backend="omnivoice", ready=False, detail="missing transformers", checks=[])
    ready_vox = TtsReadiness(backend="voxcpme", ready=True, detail="ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: blocked_omni)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready_vox)
    monkeypatch.setattr(cli_mod, "builtin_backends", lambda: ("omnivoice", "voxcpme"))

    result = runner.invoke(main, ["doctor"])
    assert result.exit_code != 0, result.output
    assert "doctor found missing prerequisites" in result.output
    assert "doctor lanes:" in result.output
    assert "ready=`dub ja2zh`" in result.output
    assert "blocked=`dub en2zh`" in result.output
    assert "ready for `dub auto`, `dub en2zh`, `dub ja2zh`" not in result.output


def test_dub_doctor_failure_message_still_names_lane(runner, monkeypatch, tmp_path):
    """AC-3: when prerequisites are missing, the failure path should still
    name the lane in the message that surfaces, so the operator knows which
    flow the failure applies to.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = runner.invoke(main, ["doctor", "--config", str(cfg)])
    assert result.exit_code != 0
    assert "doctor found missing prerequisites" in result.output
    # AC-3 still does not require the success message on the failure path,
    # but the failure must still point the operator at the auto path.
    assert "gemini_api_key: MISSING" in result.output


def test_en2zh_default_project_dir_is_video_stem_dub_next_to_input(
    runner, tmp_path, monkeypatch
):
    """AC-1/AC-2: `dub en2zh <VIDEO>` (no flags) should auto-derive the
    project directory as `<video-stem>.dub/` next to the source video, so
    the operator can predict the output path without reading config.
    """
    from dub.cli import _default_auto_project_dir

    video = tmp_path / "my_talk.mp4"
    video.write_bytes(b"fake")
    expected = tmp_path / "my_talk.dub"
    assert _default_auto_project_dir(video) == expected

    # Same default for ja2zh
    video2 = tmp_path / "my_anime.mkv"
    video2.write_bytes(b"fake")
    assert _default_auto_project_dir(video2) == tmp_path / "my_anime.dub"


def test_en2zh_help_documents_default_project_dir(runner):
    """AC-1: the --help text must explicitly document the default
    project-dir derivation so the operator does not have to read code.
    """
    result = runner.invoke(main, ["en2zh", "--help"])
    assert result.exit_code == 0
    assert "<video-stem>.dub/" in result.output
    assert "next to the input video" in result.output

    result_ja = runner.invoke(main, ["ja2zh", "--help"])
    assert result_ja.exit_code == 0
    assert "<video-stem>.dub/" in result_ja.output


def test_en2zh_zero_flag_invocation_lands_project_next_to_video(
    runner, tmp_path, monkeypatch
):
    """AC-1/AC-2: invoking `dub en2zh <VIDEO>` with no --project-dir
    flag must place the project at `<video-stem>.dub/` next to the
    source video. We monkeypatch the network-bound pieces
    (project_input_info, run_pipeline) so the test stays a pure CLI
    wiring test, but the project-dir derivation is the contract under
    test here.
    """
    video = tmp_path / "auto_talk.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "auto_talk.dub"

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
        ["en2zh", str(video), "--config", str(cfg), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert f"project={project_dir}" in result.output
    # The video must have been copied into the auto-derived project dir
    assert (project_dir / "01_raw_video" / "video.mp4").exists()


def test_ja2zh_zero_flag_invocation_lands_project_next_to_video(
    runner, tmp_path, monkeypatch
):
    """Symmetric to en2zh: `dub ja2zh <VIDEO>` should also default
    project-dir to <video-stem>.dub/ next to the input.
    """
    video = tmp_path / "anime_clip.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "anime_clip.dub"

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
        ["ja2zh", str(video), "--config", str(cfg), "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert f"project={project_dir}" in result.output


def test_en2zh_explicit_project_dir_still_wins(runner, tmp_path, monkeypatch):
    """Backward-compat: when the operator passes --project-dir
    explicitly, that path is used (not the auto-derived default)."""
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"fake")
    explicit = tmp_path / "my-explicit-proj"

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
        "video_path": str(explicit / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *args, **kwargs: {"ok": True})

    result = runner.invoke(
        main,
        [
            "en2zh", str(video),
            "--project-dir", str(explicit),
            "--config", str(cfg),
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert f"project={explicit}" in result.output
    # The default-derived path must NOT have been created
    assert not (tmp_path / "talk.dub").exists()


# ---------------------------------------------------------------------------
# AUTO-S2: Centralized preflight contract — failure & shared-contract tests
# ---------------------------------------------------------------------------
#
# AUTO-S2 is the second slice of the auto-workflow wave. T6 (AUTO-S1) shipped
# the `dub auto` entrypoint that funnels into `_run_pipeline_command`, which
# is shared with `dub en2zh`, `dub ja2zh`, and the legacy `dub run`. The
# centralized preflight is `_run_preflight(project_dir, cfg, source_lang)`,
# and it gates *every* auto-workflow surface on the same set of
# prerequisites (ffmpeg, ffprobe, pipeline_scripts, gemini_key when
# translate-mode=delegate, and the TTS backend that owns the resolved
# source-lang).
#
# The tests below prove the contract from the operator's seat: a single
# failure must surface in *every* entrypoint that funnels through the same
# pipeline dispatcher, and a successful run must show the per-gate status
# for all shared gates plus the route-specific TTS gate.
# ---------------------------------------------------------------------------


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        "paths:\n"
        "  qwenasr_cli: /bin/true\n"
        "  omnivoice_python: /bin/true\n"
        "  skills_dir: /tmp/vendor/pipeline_scripts\n"
        "  translation_skill: /bin/true\n",
        encoding="utf-8",
    )


def _stub_pipeline_dependencies(monkeypatch, tmp_path, project_dir):
    """Stub the network-bound pieces so preflight is the only gate under test.

    Returns the project_dir path used by the stub.
    """
    monkeypatch.setattr("dub.cli.project_input_info", lambda _: {
        "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *args, **kwargs: {"ok": True})


def _make_ok_preflight_patches(monkeypatch):
    """Make every shared preflight gate report OK; only the TTS gate is
    the caller's responsibility to set per-route."""
    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/scripts"))


def test_run_preflight_fails_fast_when_ffmpeg_missing(runner, tmp_path, monkeypatch):
    """AUTO-S2 AC-fail-1: when ffmpeg is missing, every entrypoint that
    funnels through `_run_pipeline_command` must fail fast *before* any
    stage work begins, with a single UserError message that lists the
    missing ffmpeg gate so the operator can fix it in one pass.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])

    def _ffmpeg_missing(name):
        # ffmpeg/ffprobe fail; everything else passes
        if name in ("ffmpeg", "ffprobe"):
            return (False, "missing")
        return (True, "/bin/fake")

    monkeypatch.setattr("dub.cli._which_status", _ffmpeg_missing)
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/scripts"))
    # Stub out project_input_info — the real one shells out to ffprobe
    # to compute duration, but the preflight contract is what we are
    # testing here, not the bootstrap probe.
    monkeypatch.setattr("dub.cli.project_input_info", lambda _p: {
        "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })

    ready = TtsReadiness(backend="voxcpme", ready=True, detail="fake-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready)
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *a, **kw: {"ok": True})

    pipeline_called = {"n": 0}
    def _spy_run_pipeline(*args, **kwargs):
        pipeline_called["n"] += 1
        return {"ok": True}
    monkeypatch.setattr("dub.cli.run_pipeline", _spy_run_pipeline)

    result = runner.invoke(
        main,
        [
            "ja2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code != 0, result.output
    # Pipeline must not have been invoked — fail-fast is the contract.
    assert pipeline_called["n"] == 0
    # ffmpeg gate is named in the failure message.
    assert "ffmpeg" in result.output
    assert "ffprobe" in result.output
    assert "preflight failed" in result.output


def test_run_preflight_fails_fast_when_gemini_key_missing(runner, tmp_path, monkeypatch):
    """AUTO-S2 AC-fail-2: with translate-mode=delegate, missing GOOGLE_API_KEY
    must be caught at the preflight stage so we never shell out to the
    translator only to discover the secret is unset.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/scripts"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("dub.cli.project_input_info", lambda _p: {
        "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })

    ready = TtsReadiness(backend="voxcpme", ready=True, detail="fake-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready)

    pipeline_called = {"n": 0}
    monkeypatch.setattr(
        "dub.cli.run_pipeline",
        lambda *a, **kw: (pipeline_called.__setitem__("n", pipeline_called["n"] + 1) or {"ok": True}),
    )

    result = runner.invoke(
        main,
        [
            "en2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code != 0, result.output
    assert pipeline_called["n"] == 0
    assert "gemini_key" in result.output
    assert "preflight failed" in result.output
    # The TTS gate is OK in this test, so it must not appear in the
    # failure bullets — but the success preflight path that prints the
    # TTS gate is gated behind the failure raise, so we instead prove
    # the contract by asserting the failure message *only* lists the
    # gemini_key gate, not the TTS one.
    assert "tts.omnivoice" not in result.output
    assert "GOOGLE_API_KEY,GEMINI_API_KEY" in result.output


def test_run_preflight_fails_fast_when_tts_backend_not_ready(runner, tmp_path, monkeypatch):
    """AUTO-S2 AC-fail-3: the route-specific TTS backend (omnivoice for en,
    voxcpme for ja) must be READY. If not, the preflight must fail with
    the failing backend named in the message so the operator knows
    which route is blocked.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])
    monkeypatch.setattr("dub.cli._which_status", lambda _name: (True, "/bin/fake"))
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (True, "/fake/scripts"))
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    # OmniVoice not ready (en route), VoxCPM ready (ja route)
    blocked_omni = TtsReadiness(
        backend="omnivoice", ready=False, detail="interpreter missing", checks=[]
    )
    ready_vox = TtsReadiness(backend="voxcpme", ready=True, detail="ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: blocked_omni)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready_vox)
    # Stub project_input_info for both invocations below (one fails, one passes).
    monkeypatch.setattr("dub.cli.project_input_info", lambda _p: {
        "video_path": str(_p / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })

    pipeline_called = {"n": 0}
    monkeypatch.setattr(
        "dub.cli.run_pipeline",
        lambda *a, **kw: (pipeline_called.__setitem__("n", pipeline_called["n"] + 1) or {"ok": True}),
    )

    # en2zh: must fail because omnivoice is blocked
    result_en = runner.invoke(
        main,
        [
            "en2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )
    assert result_en.exit_code != 0, result_en.output
    assert "tts.omnivoice" in result_en.output
    assert "interpreter missing" in result_en.output

    # ja2zh: must succeed (voxcpme is ready) and the success preflight
    # line must list tts.voxcpme as the route's TTS gate.
    result_ja = runner.invoke(
        main,
        [
            "ja2zh", str(video),
            "--project-dir", str(tmp_path / "proj_ja"),
            "--config", str(cfg),
            "--yes",
        ],
    )
    assert result_ja.exit_code == 0, result_ja.output
    assert "tts.voxcpme=ok" in result_ja.output


def test_run_preflight_reports_all_failing_gates_at_once(runner, tmp_path, monkeypatch):
    """AUTO-S2 AC-fail-4: the operator must not be drip-fed one failure at
    a time. If three gates are failing, the message must list all three
    so they can be fixed in one pass.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    monkeypatch.setattr("dub.cli._auto_recover_missing_secrets", lambda: [])

    def _ffmpeg_fail(name):
        if name in ("ffmpeg", "ffprobe"):
            return (False, "missing")
        return (True, "/bin/fake")

    monkeypatch.setattr("dub.cli._which_status", _ffmpeg_fail)
    monkeypatch.setattr("dub.cli._path_status", lambda _p: (False, "/no/scripts"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    blocked_omni = TtsReadiness(
        backend="omnivoice", ready=False, detail="interp missing", checks=[]
    )
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: blocked_omni)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: blocked_omni)
    monkeypatch.setattr("dub.cli.project_input_info", lambda _p: {
        "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
        "video_sha256": "abc",
        "duration_sec": 1.23,
    })
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *a, **kw: {"ok": True})

    result = runner.invoke(
        main,
        [
            "en2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
        ],
    )

    assert result.exit_code != 0, result.output
    # All four gates should be in the message:
    assert "ffmpeg" in result.output
    assert "ffprobe" in result.output
    assert "pipeline_scripts" in result.output
    assert "gemini_key" in result.output
    assert "tts.omnivoice" in result.output


@pytest.mark.parametrize(
    "route_cmd,route_args,expected_src,expected_tts_gate",
    [
        # (extra args after the video, expected src= token, expected tts gate)
        (["en2zh"], [], "en", "tts.omnivoice"),
        (["ja2zh"], [], "ja", "tts.voxcpme"),
        (
            ["auto"],
            ["--source-lang", "en"],
            "en",
            "tts.omnivoice",
        ),
        (
            ["auto"],
            ["--source-lang", "ja"],
            "ja",
            "tts.voxcpme",
        ),
    ],
)
def test_run_preflight_routes_to_correct_tts_backend_for_each_entrypoint(
    runner, tmp_path, monkeypatch, route_cmd, route_args, expected_src, expected_tts_gate,
):
    """AUTO-S2 AC-share-1: dub auto, dub en2zh, and dub ja2zh all funnel
    through `_run_pipeline_command` and therefore share the centralized
    preflight contract. The success-line preflight output must name the
    source lang AND the TTS gate that owns that source lang, so an
    operator reading the line can predict which backend is in use
    without grepping the code.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / f"{expected_src}_video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / f"{expected_src}_proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    _make_ok_preflight_patches(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    _stub_pipeline_dependencies(monkeypatch, tmp_path, project_dir)

    # Both TTS backends must be READY for the route under test to pass.
    ready_omni = TtsReadiness(
        backend="omnivoice", ready=True, detail="omni-ready", checks=[]
    )
    ready_vox = TtsReadiness(backend="voxcpme", ready=True, detail="vox-ready", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready_omni)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready_vox)

    result = runner.invoke(
        main,
        [
            route_cmd[0], str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--yes",
            *route_args,
        ],
    )

    assert result.exit_code == 0, result.output
    preflight_lines = [
        line for line in result.output.splitlines()
        if line.startswith("preflight:")
    ]
    assert len(preflight_lines) == 1, result.output
    preflight = preflight_lines[0]
    assert f"src={expected_src}" in preflight
    assert expected_tts_gate in preflight
    # TTS gate must be reported as ok, not fail.
    assert f"{expected_tts_gate}=ok" in preflight


def test_run_preflight_shared_by_legacy_dub_run_command(runner, tmp_path, monkeypatch):
    """AUTO-S2 AC-share-2: the legacy `dub run` command must also use the
    centralized preflight contract — the plan explicitly says
    'dub auto and route-specific commands share the same preflight
    contract' but in practice the only way to guarantee that is to
    also share it with the lower-level `dub run` command, since that
    is the dispatcher entrypoint.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj"
    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    _make_ok_preflight_patches(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    _stub_pipeline_dependencies(monkeypatch, tmp_path, project_dir)

    ready_omni = TtsReadiness(backend="omnivoice", ready=True, detail="ok", checks=[])
    ready_vox = TtsReadiness(backend="voxcpme", ready=True, detail="ok", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready_omni)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready_vox)

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
    preflight_lines = [
        line for line in result.output.splitlines()
        if line.startswith("preflight:")
    ]
    assert len(preflight_lines) == 1, result.output
    preflight = preflight_lines[0]
    # All shared gates must be on the success line.
    for gate in ("ffmpeg=ok", "ffprobe=ok", "pipeline_scripts=ok", "gemini_key=ok", "tts.omnivoice=ok"):
        assert gate in preflight, f"missing {gate!r} in preflight: {preflight!r}"


def test_tts_backend_for_source_raises_usererror_for_unsupported_source():
    """AUTO-S2 AC-share-3: the dispatch table is the single source of
    truth for which TTS backend owns a given source lang. Asking for a
    source lang outside the productized surface must raise UserError
    so the operator gets a clean failure rather than a NoneType crash
    deep in the TTS stage.
    """
    from dub.cli import _tts_backend_for_source
    from dub.errors import UserError

    # Supported routes resolve to the right backend.
    assert _tts_backend_for_source("en") == "omnivoice"
    assert _tts_backend_for_source("ja") == "voxcpme"

    # Unsupported source lang raises UserError, not TypeError.
    with pytest.raises(UserError) as exc_info:
        _tts_backend_for_source("fr")
    assert "fr" in str(exc_info.value)
    assert "no TTS route registered" in str(exc_info.value)


def test_run_preflight_success_line_includes_route_summary_for_each_mode(
    runner, tmp_path, monkeypatch,
):
    """AUTO-S2 AC-share-4: the success preflight line must include the
    route summary (mode=... route=...) for every translate mode that
    `dub auto` accepts, so an operator can read one line and know
    exactly what pipeline is about to run.
    """
    import dub.cli as cli_mod
    from dub.tts_engines.contract import TtsReadiness

    cfg = tmp_path / "cfg.yaml"
    _write_minimal_config(cfg)

    _make_ok_preflight_patches(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    ready_vox = TtsReadiness(backend="voxcpme", ready=True, detail="ok", checks=[])
    monkeypatch.setattr(cli_mod, "omnivoice_readiness", lambda _cfg: ready_vox)
    monkeypatch.setattr(cli_mod, "voxcpme_readiness", lambda _cfg: ready_vox)

    # translate-mode=use-existing needs an external SRT on disk.
    external_srt = tmp_path / "external.zhtw.srt"
    external_srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n哈囉\n", encoding="utf-8"
    )

    def _stub(project_dir, **_):
        return {
            "video_path": str(project_dir / "01_raw_video" / "video.mp4"),
            "video_sha256": "abc",
            "duration_sec": 1.23,
        }
    monkeypatch.setattr("dub.cli.project_input_info", _stub)
    monkeypatch.setattr("dub.cli.run_pipeline", lambda *a, **kw: {"ok": True})

    # use-existing mode — route summary must mention the external srt path.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    project_dir = tmp_path / "proj_ue"
    result_ue = runner.invoke(
        main,
        [
            "ja2zh", str(video),
            "--project-dir", str(project_dir),
            "--config", str(cfg),
            "--translate-mode", "use-existing",
            "--translated-srt", str(external_srt),
            "--yes",
        ],
    )
    assert result_ue.exit_code == 0, result_ue.output
    preflight_lines = [
        line for line in result_ue.output.splitlines()
        if line.startswith("preflight:")
    ]
    assert len(preflight_lines) == 1
    preflight = preflight_lines[0]
    assert "mode=use-existing" in preflight
    assert "external_srt=" in preflight
    assert str(external_srt) in preflight
