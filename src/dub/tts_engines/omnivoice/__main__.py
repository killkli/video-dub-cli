"""Repo-owned OmniVoice TTS runtime entrypoint.

Invoking ``python -m dub.tts_engines.omnivoice`` runs the OmniVoice
Stage 5 batch TTS script. All CLI arguments are forwarded unchanged
to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts.py``.

This is the canonical invocation path for a fresh operator: the
runner resolves the vendored script inside the repo (no separate
``skills_dir`` configuration, no external skill clone). The minimal
``omnivoice`` inference package is vendored under ``src/omnivoice``
in this repo, while the heavy OmniVoice runtime deps should live in
whatever interpreter ``paths.omnivoice_python`` points at. ``dub doctor``
verifies that interpreter can import both ``torch`` and
``omnivoice.models.omnivoice``.
"""
from __future__ import annotations

from dub.tts_engines.omnivoice.runner import main


__all__ = ["main"]


if __name__ == "__main__":
    main()
