"""Repo-owned VoxCPM TTS runtime entrypoint.

Invoking ``python -m dub.tts_engines.voxcpme`` runs the VoxCPM
Stage 5 batch TTS script. All CLI arguments are forwarded unchanged
to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``.

This is the canonical invocation path for a fresh operator: the
runner resolves the vendored script inside the repo (no separate
``skills_dir`` configuration, no external skill clone), and the
``gradio_client`` + ``opencc`` deps are pulled in via the
``[tts-vox]`` extra. The local VoxCPM gradio server (default
``127.0.0.1:8808``) is the one bootstrap-runtime prerequisite
``dub doctor`` still surfaces explicitly — it is the heavy model
stack this repo does not (yet) ship.
"""
from __future__ import annotations

from dub.tts_engines.voxcpme.runner import main


__all__ = ["main"]


if __name__ == "__main__":
    main()
