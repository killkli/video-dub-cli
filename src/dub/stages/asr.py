"""stages/asr.py — Stage 2: ASR transcription using repo-owned qwenasr_mlx_cli.

Test escape hatch
-----------------
The vendored qwenasr_mlx_cli pipeline requires real ASR model weights, which
integration tests cannot bundle. To keep the integration suite hermetic without
shelling out to a fake CLI (the old design), the stage honours two opt-in
escape hatches that are no-ops in production unless a test harness or
operator script explicitly opts in:

* ``config.paths.asr_test_fixture_srt`` (or env ``DUB_ASR_TEST_FIXTURE_SRT``)
  — when set to a readable SRT path, the stage copies that file's contents
  to ``03_asr/video.srt`` instead of running the real MLX pipeline.
* ``config.paths.asr_test_backend_fail`` (or env ``DUB_ASR_TEST_BACKEND_FAIL``)
  — when set to a truthy value, the stage short-circuits to a deterministic
  failed state, exercising the failure path.

Both knobs are documented in ``docs/standalone-operator.md``. The config
field takes precedence over the env var when both are set, so a per-project
YAML can override the system-wide env.
"""

from __future__ import annotations

import os
from pathlib import Path

from dub.config import DubConfig
from dub.state import now_iso
from dub.stages.base import Stage, StageState
from qwenasr_mlx_cli.core.exceptions import ASRProcessingError, BackendUnavailableError, InputValidationError
from qwenasr_mlx_cli.core.types import SubtitleConfig
from qwenasr_mlx_cli.pipelines.transcribe import run_transcription


_TEST_FIXTURE_ENV = "DUB_ASR_TEST_FIXTURE_SRT"
_TEST_FAIL_ENV = "DUB_ASR_TEST_BACKEND_FAIL"


def _resolve_test_fixture_srt(config: DubConfig) -> str | None:
    """Return the opt-in fixture SRT path, or None when no test hatch is set.

    Order: ``config.paths.asr_test_fixture_srt`` (truthy str) → env var.
    """
    field = getattr(config.paths, "asr_test_fixture_srt", None)
    if field:
        return str(field)
    return os.environ.get(_TEST_FIXTURE_ENV) or None


def _resolve_test_backend_fail(config: DubConfig) -> bool:
    """Return True when the test-fail hatch is opted in."""
    field = getattr(config.paths, "asr_test_backend_fail", None)
    if field:
        return True
    return bool(os.environ.get(_TEST_FAIL_ENV))


class AsrStage(Stage):
    name = "02_asr"

    def is_done(self, project_dir: Path) -> bool:
        srt_path = project_dir / "03_asr" / "video.srt"
        return srt_path.exists()

    def run(self, project_dir: Path, config: DubConfig) -> StageState:
        state = StageState(name=self.name, status="running", started_at=now_iso())
        state.attempts = 1

        input_video = project_dir / "01_raw_video" / "video.mp4"
        srt_out = project_dir / "03_asr" / "video.srt"
        log_file = project_dir / ".dub" / f"{self.name}.log"

        srt_out.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # --- test escape hatches (opt-in via config or env; no-ops in production) ---
        fixture = _resolve_test_fixture_srt(config)
        if fixture:
            fixture_path = Path(fixture)
            if not fixture_path.is_file():
                state.status = "failed"
                state.finished_at = now_iso()
                state.error = (
                    f"test fixture SRT not found at {fixture_path} "
                    f"(see _TEST_FIXTURE_ENV / paths.asr_test_fixture_srt)"
                )
                return state
            rendered = fixture_path.read_text(encoding="utf-8")
            log_file.write_text(
                f"test-mode: copied fixture SRT from {fixture_path}\n",
                encoding="utf-8",
            )
            srt_out.write_text(rendered, encoding="utf-8")
            state.artifacts = ["video.srt"]
            state.output_dir = "03_asr"
            state.status = "done"
            state.finished_at = now_iso()
            return state

        if _resolve_test_backend_fail(config):
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = (
                "test-mode forced backend failure "
                "(see _TEST_FAIL_ENV / paths.asr_test_backend_fail)"
            )
            log_file.write_text(state.error + "\n", encoding="utf-8")
            return state

        # --- real repo-owned ASR pipeline ---
        subtitle_config = SubtitleConfig(output_format="srt")
        try:
            rendered = run_transcription(
                input_path=input_video,
                backend_name="mlx",
                output_format="srt",
                language=config.defaults.source_lang or None,
                prompt=None,
                subtitle_config=subtitle_config,
                convert_simplified_to_traditional=False,
            )
        except (BackendUnavailableError, InputValidationError, ASRProcessingError, NotImplementedError) as exc:
            log_file.write_text(f"ERROR: {exc}\n", encoding="utf-8")
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"repo ASR pipeline failed: {exc}; see {log_file}"
            return state
        except Exception as exc:
            log_file.write_text(f"UNEXPECTED ERROR: {exc}\n", encoding="utf-8")
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"repo ASR pipeline failed: {exc}; see {log_file}"
            return state

        srt_out.write_text(rendered, encoding="utf-8")
        log_file.write_text("repo ASR pipeline completed\n", encoding="utf-8")

        if not srt_out.exists() or not srt_out.read_text(encoding="utf-8").strip():
            state.status = "failed"
            state.finished_at = now_iso()
            state.error = f"repo ASR pipeline produced empty SRT; see {log_file}"
            return state

        state.artifacts = ["video.srt"]
        state.output_dir = "03_asr"
        state.status = "done"
        state.finished_at = now_iso()
        return state