"""runner.py — pipeline orchestrator: runs 6 stages sequentially with state + retry."""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from dub.config import DubConfig
from dub.stages import (
    StemsStage,
    AsrStage,
    RefAudioStage,
    TranslateStage,
    TtsStage,
    AssembleStage,
)
from dub.stages.base import Stage
from dub import state as state_module
from dub.state import ProjectState, StageState, now_iso


def _artifacts_intact(project_dir: Path, stage_state: StageState) -> bool:
    """Return True when recorded stage artifacts still exist on disk."""
    if not stage_state.output_dir or not stage_state.artifacts:
        return False
    out_dir = project_dir / stage_state.output_dir
    return out_dir.exists() and all((out_dir / name).exists() for name in stage_state.artifacts)


def run_pipeline(
    project_dir: Path,
    config: DubConfig,
    *,
    yes: bool = False,
) -> dict:
    """Run the full 6-stage dubbing pipeline and return final state as dict."""
    try:
        s = state_module.load_state(project_dir)
        s = state_module.reset_running_to_pending(s)
    except FileNotFoundError:
        s = state_module.new_state(project_dir, config)

    stages: list[Stage] = [
        StemsStage(),
        AsrStage(),
        RefAudioStage(),
        TranslateStage(),
        TtsStage(),
        AssembleStage(),
    ]

    for st in stages:
        if st.name not in s.stages:
            s.stages[st.name] = StageState()

    state_module.save_state(project_dir, s)

    for stage in stages:
        log = logger.bind(stage=stage.name)
        stage_state = s.stages[stage.name]

        can_skip = stage.is_done(project_dir)
        if can_skip and stage_state.status in {"done", "skipped"} and stage_state.artifacts:
            can_skip = _artifacts_intact(project_dir, stage_state)

        if can_skip:
            stage_state.status = "skipped"
            stage_state.finished_at = now_iso()
            state_module.save_state(project_dir, s)
            log.info(f"[{stage.name}] skipped (already done)")
            continue

        stage_state.status = "running"
        stage_state.started_at = now_iso()
        stage_state.attempts += 1
        state_module.save_state(project_dir, s)
        log.info(f"[{stage.name}] starting")

        try:
            new_state = _run_stage_with_retry(stage, project_dir, config, log)
        except Exception as exc:
            log.error(f"[{stage.name}] failed: {exc}")
            stage_state.status = "failed"
            stage_state.error = str(exc)
            state_module.save_state(project_dir, s)
            raise

        s.stages[stage.name] = new_state
        if new_state.status == "done" and not new_state.finished_at:
            s.stages[stage.name].finished_at = now_iso()
        state_module.save_state(project_dir, s)
        log.info(f"[{stage.name}] done")

    s.updated_at = now_iso()
    state_module.save_state(project_dir, s)
    return s.to_dict()


def _run_stage_with_retry(
    stage: Stage,
    project_dir: Path,
    config: DubConfig,
    log,
) -> StageState:
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
