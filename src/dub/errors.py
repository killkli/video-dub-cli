"""errors.py — public exception hierarchy for video-dub-cli."""

from __future__ import annotations


class DubError(Exception):
    """Base for all dub-cli errors."""

    def exit_code(self) -> int:
        return 1


class UserError(DubError):
    """User misconfiguration / invalid input — not retryable."""

    def exit_code(self) -> int:
        return 2


class StageError(DubError):
    """Stage failed after all retry attempts."""

    def exit_code(self) -> int:
        return 2


class TranslationError(DubError):
    """Translation sub-agent failure."""

    def exit_code(self) -> int:
        return 2


class ConfigError(UserError):
    """Malformed config file or conflicting options."""