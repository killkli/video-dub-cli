"""T6e: Phase 4 route scenario coverage — delegate/use-existing/skip/ja routes.

Validates:
  - fresh run with translate=delegate writes translated subtitle + state
  - fresh run with translate=use-existing copies external subtitle into project
  - existing project can resume with translate=skip using in-project translated subtitle
  - ja->zh route uses the VoxCPM script contract (--ja-srt + --project-dir)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import os

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
TEST_SHORT = FIXTURES / "test_short.mp4"


def _run_dub(
    video: Path,
    project_dir: Path,
    config_path: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    cfg_text = config_path.read_text(encoding="utf-8")
    skills_dir = None
    for line in cfg_text.splitlines():
        if line.strip().startswith("skills_dir:"):
            skills_dir = line.split(":", 1)[1].strip()
            break
    env = dict(os.environ)
    env["DUB_ASR_TEST_FIXTURE_SRT"] = str(config_path.parent / "fake-asr.srt")
    if skills_dir:
        env["DUB_PIPELINE_SCRIPTS_DIR"] = skills_dir
    return subprocess.run(
        [
            "dub",
            "run",
            str(video),
            "--project-dir",
            str(project_dir),
            "--config",
            str(config_path),
            "--yes",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@pytest.mark.integration
def test_6e_delegate_fresh_run_records_translated_subtitle_contract(
    tmp_path: Path,
    fake_qwenasr_config: Path,
) -> None:
    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "delegate-proj"
    result = _run_dub(
        TEST_SHORT,
        project_dir,
        fake_qwenasr_config,
        "--source-lang",
        "en",
        "--target-lang",
        "zh",
        "--translate-mode",
        "delegate",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "translate=delegate provider=mock" in result.stdout
    assert f"preflight: src=en tgt=zh project={project_dir}" in result.stdout

    zh_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"
    assert zh_srt.exists(), "delegate route should materialize translated subtitle in project"
    content = _read(zh_srt)
    assert "[ZH]" in content, "mock translation provider should mark translated lines"

    validate = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert validate.returncode == 0, validate.stderr or validate.stdout
    assert "mode=delegate translate_status=done" in validate.stdout


@pytest.mark.integration
def test_6e_use_existing_fresh_run_copies_external_srt_into_project(
    tmp_path: Path,
    fake_qwenasr_config: Path,
) -> None:
    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "use-existing-proj"
    external_srt = tmp_path / "external.zhtw.srt"
    external_srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n這是外部提供的中文字幕。\n",
        encoding="utf-8",
    )

    result = _run_dub(
        TEST_SHORT,
        project_dir,
        fake_qwenasr_config,
        "--source-lang",
        "en",
        "--target-lang",
        "zh",
        "--translate-mode",
        "use-existing",
        "--translated-srt",
        str(external_srt),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert f"translate=use-existing external_srt={external_srt}" in result.stdout
    assert f"run complete: project={project_dir}" in result.stdout

    project_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"
    primary_srt = project_dir / "05_translate" / "video.zhtw.srt"
    assert project_srt.exists(), "use-existing route should copy translated subtitle into canonical project path"
    assert primary_srt.exists(), "use-existing route should also populate primary translate artifact"
    assert _read(project_srt) == _read(external_srt)
    assert _read(primary_srt) == _read(external_srt)

    validate = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert validate.returncode == 0, validate.stderr or validate.stdout
    assert "mode=use-existing translate_status=done" in validate.stdout


@pytest.mark.integration
def test_6e_skip_resume_reuses_existing_project_translated_subtitle(
    tmp_path: Path,
    fake_qwenasr_config: Path,
) -> None:
    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "skip-proj"
    first = _run_dub(
        TEST_SHORT,
        project_dir,
        fake_qwenasr_config,
        "--source-lang",
        "en",
        "--target-lang",
        "zh",
        "--translate-mode",
        "delegate",
    )
    assert first.returncode == 0, first.stderr or first.stdout

    project_srt = project_dir / "05_translated_srt" / "video.zhtw.srt"
    assert project_srt.exists()
    before = _read(project_srt)

    tts_dir = project_dir / "06_tts_wav"
    shutil.rmtree(tts_dir)
    tts_dir.mkdir(parents=True, exist_ok=True)

    rerun = _run_dub(
        TEST_SHORT,
        project_dir,
        fake_qwenasr_config,
        "--source-lang",
        "en",
        "--target-lang",
        "zh",
        "--translate-mode",
        "skip",
    )
    assert rerun.returncode == 0, rerun.stderr or rerun.stdout
    assert "translate=skip existing_project_srt=" in rerun.stdout
    assert f"run complete: project={project_dir}" in rerun.stdout

    after = _read(project_srt)
    assert after == before, "skip route should reuse in-project translated subtitle instead of replacing it"
    assert any(tts_dir.glob("line_*_tts.wav")), "skip rerun should rebuild downstream TTS outputs"

    validate = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert validate.returncode == 0, validate.stderr or validate.stdout
    assert "mode=skip translate_status=skipped" in validate.stdout


@pytest.mark.integration
def test_6e_ja_route_uses_vox_script_contract(
    tmp_path: Path,
    fake_qwenasr_config: Path,
) -> None:
    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    project_dir = tmp_path / "ja-proj"
    result = _run_dub(
        TEST_SHORT,
        project_dir,
        fake_qwenasr_config,
        "--source-lang",
        "ja",
        "--target-lang",
        "zh",
        "--translate-mode",
        "delegate",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert f"preflight: src=ja tgt=zh project={project_dir}" in result.stdout
    assert "translate=delegate provider=mock" in result.stdout

    asr_srt = project_dir / "03_asr" / "video.srt"
    assert asr_srt.exists()
    assert "哈囉，歡迎來到課堂。" in _read(project_dir / "05_translated_srt" / "video.zhtw.srt")

    tts_log = _read(project_dir / ".dub" / "05_tts.log")
    assert "--ja-srt" in tts_log, "ja route must invoke VoxCPM contract with --ja-srt"
    assert "--project-dir" in tts_log, "ja route must pass --project-dir to VoxCPM script"
    assert str(asr_srt) in tts_log, "ja route should wire original ASR subtitle as ref_text source"

    validate = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert validate.returncode == 0, validate.stderr or validate.stdout
    assert "mode=delegate translate_status=done" in validate.stdout


@pytest.mark.integration
def test_6e_en2zh_alias_runs_supported_fake_backend_flow(
    tmp_path: Path,
    fake_qwenasr_config: Path,
) -> None:
    if not TEST_SHORT.exists():
        pytest.skip(f"Fixture not found: {TEST_SHORT}")

    cfg_text = fake_qwenasr_config.read_text(encoding="utf-8")
    skills_dir = None
    for line in cfg_text.splitlines():
        if line.strip().startswith("skills_dir:"):
            skills_dir = line.split(":", 1)[1].strip()
            break

    env = dict(os.environ)
    env["DUB_ASR_TEST_FIXTURE_SRT"] = str(fake_qwenasr_config.parent / "fake-asr.srt")
    if skills_dir:
        env["DUB_PIPELINE_SCRIPTS_DIR"] = skills_dir

    project_dir = tmp_path / "en2zh-alias-proj"
    result = subprocess.run(
        [
            "dub",
            "en2zh",
            str(TEST_SHORT),
            "--project-dir",
            str(project_dir),
            "--config",
            str(fake_qwenasr_config),
            "--yes",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert f"preflight: src=en tgt=zh project={project_dir}" in result.stdout
    assert "translate=delegate provider=mock" in result.stdout
    assert f"run complete: project={project_dir}" in result.stdout

    validate = subprocess.run(
        ["dub", "validate", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert validate.returncode == 0, validate.stderr or validate.stdout
    assert "mode=delegate translate_status=done" in validate.stdout
