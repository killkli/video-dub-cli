"""Repo-owned VoxCPM TTS runtime entrypoint.

Invoking ``python -m dub.tts_engines.voxcpme`` runs the VoxCPM
Stage 5 batch TTS script. All CLI arguments are forwarded unchanged
to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``.

This is the canonical invocation path for a fresh operator. The
gradio_client + opencc deps are pulled in via the ``[tts-vox]``
extra; the local VoxCPM gradio server (default 127.0.0.1:8808) is
the one bootstrap-runtime prerequisite we do not pretend to own.
"""
from __future__ import annotations

from dub.tts_engines.voxcpme.runner import main


if __name__ == "__main__":
    main()
