"""logging.py — loguru setup with stdout (human/json) + file (debug)."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from dub.config import LoggingConfig


def setup_logging(config: LoggingConfig, log_file: Path) -> None:
    """
    Configure loguru:

    - stdout: human-readable (colorized timestamp + level + message)
              OR JSON-serialized lines when config.json_logs is True
    - log_file: always DEBUG level, machine-parseable format
    """
    logger.remove()

    if config.json_logs:
        logger.add(
            sys.stdout,
            serialize=True,
            level=config.level,
        )
    else:
        logger.add(
            sys.stdout,
            level=config.level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        )

    logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} — {message}",
        rotation="10 MB",
        retention="7 days",
    )


def stage_logger(stage_name: str):
    """
    Return a logger bind()ed with stage context.
    Usage: logger.bind(stage="02_asr").info("starting ASR")
    """
    return logger.bind(stage=stage_name)