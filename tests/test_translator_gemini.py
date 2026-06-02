from __future__ import annotations

import os

import pytest

from dub.errors import TranslationError
from dub.translator_gemini import _load_api_key


def test_load_api_key_prefers_configured_env_var(monkeypatch):
    monkeypatch.setenv("CUSTOM_GEMINI_KEY", "abc123")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert _load_api_key("CUSTOM_GEMINI_KEY") == "abc123"


def test_load_api_key_falls_back_between_google_and_gemini(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-xyz")

    assert _load_api_key("GOOGLE_API_KEY") == "gemini-xyz"


def test_load_api_key_requires_environment_only(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    hermes_env = tmp_path / ".hermes" / ".env"
    hermes_env.parent.mkdir(parents=True, exist_ok=True)
    hermes_env.write_text("GOOGLE_API_KEY=should_not_be_used\n", encoding="utf-8")

    with pytest.raises(TranslationError, match="not found in environment"):
        _load_api_key("GOOGLE_API_KEY")
