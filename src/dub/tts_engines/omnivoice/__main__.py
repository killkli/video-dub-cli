"""Repo-owned OmniVoice TTS runtime entrypoint.

Invoking ``python -m dub.tts_engines.omnivoice`` runs the OmniVoice
Stage 5 batch TTS script. All CLI arguments are forwarded unchanged
to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts.py``.

This is the canonical invocation path for a fresh operator: the
runner resolves the vendored script inside the repo (no separate
``skills_dir`` configuration, no external skill clone), and the
heavy OmniVoice model stack comes in via the ``[tts-omnivoice]``
extra (``torch`` + ``torchaudio`` + the ``omnivoice`` package
itself, once published). Until ``omnivoice`` lands on PyPI, an
operator who wants the real OmniVoice route still needs to point
``paths.omnivoice_root`` (or ``DUB_OMNIVOICE_ROOT``) at a checkout
of the OmniVoice dev repo that contains a working
``omnivoice.models.omnivoice`` import. ``dub doctor`` reports
which boxes are unchecked.
"""
from __future__ import annotations

from dub.tts_engines.omnivoice.runner import main


__all__ = ["main"]


if __name__ == "__main__":
    main()
