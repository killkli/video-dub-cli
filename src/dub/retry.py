"""retry.py — tenacity-based retry decorator factory."""

from __future__ import annotations

import subprocess
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from dub.config import DubConfig


def _get_exception_by_name(name: str) -> type[Exception]:
    """Resolve a fully-qualified exception name to a class."""
    parts = name.rsplit(".", 1)
    if len(parts) == 2:
        import importlib
        mod_name, exc_name = parts
        mod = importlib.import_module(mod_name)
        return getattr(mod, exc_name)
    # Built-in
    return eval(name)  # nosec — config-driven but worker-owned


def make_retry_decorator(config: DubConfig):
    """
    Build a tenacity retry decorator from DubConfig.retry settings.
    Returns a decorator ready to be applied to a stage's run() method.
    """
    retryable = tuple(_get_exception_by_name(n) for n in config.retry.retry_on)

    return retry(
        stop=stop_after_attempt(config.retry.max_attempts),
        wait=wait_exponential(multiplier=config.retry.backoff_seconds),
        retry=retry_if_exception_type(retryable),
        reraise=True,
        before_sleep=lambda retry_state: None,  # let loguru handle logging
    )