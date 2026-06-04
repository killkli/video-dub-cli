"""Repo-owned OmniVoice TTS runtime entrypoint.

Invoking ``python -m dub.tts_engines.omnivoice`` runs the OmniVoice
Stage 5 batch TTS script. All CLI arguments are forwarded unchanged
to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts.py``.

This is the canonical invocation path for a fresh operator. No
external skill clone or extra Python interpreter is required to
launch the script; the heavy model deps (torch, torchaudio) come in
via the ``[tts-omnivoice]`` extra.
"""
from __future__ import annotations

from dub.tts_engines.omnivoice.runner import main


if __name__ == "__main__":
    main()
