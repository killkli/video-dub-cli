"""runner.py — pipeline orchestrator: runs 6 stages sequentially with state + retry."""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from dub.config import DubConfig
from dub.stages import (
    StemsStage, AsrStage, RefAudioStage,
    TranslateStage, TtsStage, AssembleStage,
)
from dub.stages.base import Stage, StageState
from dub import state as state_module
from dub.state import now_iso


def run_pipeline(
    project_dir: Path,
    config: DubConfig,
    *,
    yes: bool = False,
) -> dict:
    """
    Run the full 6-stage dubbing pipeline.

    Returns the final project state dict.
    Raises on unrecoverable failure (after all retries exhausted).
    """
    # Load or create state
    s = state_module.load_state(project_dir)
    if s is None:
        s = state_module.new_state(project_dir, config)

    stages: list[Stage] = [
        StemsStage(),
        AsrStage(),
        RefAudioStage(),
        TranslateStage(),
        TtsStage(),
        AssembleStage(),
    ]

    # Update stage list in state
    for st in stages:
        if st.name not in s["stages"]:
            s["stages"][st.name] = {"status": "pending", "attempts": 0}

    state_module.save_state(project_dir, s)

    for stage in stages:
        log = logger.bind(stage=stage.name)

        # Check skip-existing
        if stage.is_done(project_dir):
            s["stages"][stage.name]["status"] = "skipped"
            log.info(f"[{stage.name}] skipped (already done)")
            state_module.save_state(project_dir, s)
            continue

        # Mark running
        s["stages"][stage.name]["status"] = "running"
        s["stages"][stage.name]["started_at"] = now_iso()
        s["stages"][stage.name]["attempts"] = s["stages"][stage.name].get("attempts", 0) + 1
        state_module.save_state(project_dir, s)
        log.info(f"[{stage.name}] starting")

        try:
            new_state = _run_stage_with_retry(stage, project_dir, config, log)
        except Exception as exc:
            log.error(f"[{stage.name}] failed: {exc}")
            s["stages"][stage.name]["status"] = "failed"
            s["stages"][stage.name]["error"] = str(exc)
            state_module.save_state(project_dir, s)
            raise

        # Merge returned StageState into project state
        s["stages"][stage.name].update(new_state.to_dict())
        if new_state.status == "done":
            s["stages"][stage.name]["finished_at"] = now_iso()

        state_module.save_state(project_dir, s)
        log.info(f"[{stage.name}] done")

    s["updated_at"] = now_iso()
    state_module.save_state(project_dir, s)
    return s


def _run_stage_with_retry(
    stage: Stage,
    project_dir: Path,
    config: DubConfig,
    log,
) -> "StageState":
    """
    Run a stage with tenacity retry wrapping.
    Raises if all attempts exhausted.
    """
    # Import tenacity at function level to avoid import-order issues
    from tenacity import stop_after_attempt, wait_exponential, retry_if_exception_type

    retryable = (
        subprocess.CalledProcessError,
        TimeoutError,
        ConnectionError,
    )

    attempt = 0
    max_attempts = config.retry.max_attempts
    backoff = config.retry.backoff_seconds

    while True:
        attempt += 1
        try:
            return stage.run(project_dir, config)
        except retryable as exc:
            if attempt >= max_attempts:
                log.error(f"[{stage.name}] all {max_attempts} attempts exhausted")
                raise
            import time
            wait = backoff * (2 ** (attempt - 1))
            log.warning(f"[{stage.name}] attempt {attempt}/{max_attempts} failed: {exc}, waiting {wait}s")
            time.sleep(wait)