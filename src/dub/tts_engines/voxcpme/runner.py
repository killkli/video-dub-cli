#!/usr/bin/env python3
"""Package-owned VoxCPM Stage-05 runner.

This keeps the execution entrypoint inside the repo package while we
still reuse the proven heavy-lift implementation in
``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``. The wrapper is
intentionally dependency-light so it can run under the dub venv and
forward argv unchanged.

The runner is invoked two ways:

- by the active Stage 5 code in ``dub.stages.tts`` (which resolves
  it through the OmniVoice/VoxCPM adapter's :func:`build_route`).
- by a fresh operator via ``python -m dub.tts_engines.voxcpme``.

Both paths land here. The vendored script is found by walking up
from this file until a ``vendor/pipeline_scripts/`` directory is
visible; the script must be present because the stage logic depends
on it, and a missing script is a repo layout bug, not a runtime
condition.
"""
from __future__ import annotations

import runpy
from pathlib import Path


def _resolve_vendor_script(filename: str) -> Path:
    """Locate ``vendor/pipeline_scripts/<filename>`` relative to this file.

    The package lives at ``src/dub/tts_engines/voxcpme/runner.py``;
    ``parents[4]`` is the repo root, where ``vendor/`` lives. We
    walk up a few levels to be tolerant of pip install layouts that
    drop ``dub`` under ``site-packages`` (the file is the same
    module path, but we still want the vendored script to come
    from the repo rather than the install prefix).
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "vendor" / "pipeline_scripts" / filename
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate vendored TTS script {filename!r} "
        f"walking up from {here}. Repo layout invariant broken."
    )


VENDOR_SCRIPT = _resolve_vendor_script("dubbing_batch_tts_vox.py")


def main() -> None:
    runpy.run_path(str(VENDOR_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
