#!/usr/bin/env python3
"""Package-owned VoxCPM Stage-05 runner.

This keeps the execution entrypoint inside the repo package while we
still reuse the proven heavy-lift implementation in
``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``. The wrapper is
intentionally dependency-light so it can run under the dub venv and
forward argv unchanged.

The runner is invoked two ways:

- by the active Stage 5 code in ``dub.stages.tts`` (which resolves
  it through the VoxCPM adapter's :func:`build_route`).
- by a fresh operator via ``python -m dub.tts_engines.voxcpme``.

Both paths land here. The vendored script is resolved at call time
(walking up from this file until a ``vendor/pipeline_scripts/``
directory is visible) so that a missing script fails with a clear
runtime error instead of breaking ``dub`` import. Operators in
pip-install layouts (where ``dub`` lives under ``site-packages``)
get the same behaviour: we walk up from the package's installed
location, which is the same module path but a different prefix.
"""
from __future__ import annotations

import runpy
from pathlib import Path


VENDOR_SCRIPT_NAME = "dubbing_batch_tts_vox.py"


def resolve_vendor_script() -> Path:
    """Locate ``vendor/pipeline_scripts/dubbing_batch_tts_vox.py`` relative to this file.

    The package lives at ``src/dub/tts_engines/voxcpme/runner.py`` in
    the source tree; we walk up parents to find the repo root, where
    ``vendor/`` lives. The walk is also tolerant of pip-install layouts
    that drop ``dub`` under ``site-packages`` (the module path is the
    same, but the install prefix is different; we still find the
    vendored script in the source tree because it ships as package
    data alongside the installed package).

    The function is called from :func:`main` rather than at import
    time, so that a missing vendored script produces a runtime error
    with a clear message instead of breaking ``dub`` import (and
    therefore ``dub doctor``).
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "vendor" / "pipeline_scripts" / VENDOR_SCRIPT_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate vendored TTS script {VENDOR_SCRIPT_NAME!r} "
        f"walking up from {here}. Repo layout invariant broken — "
        f"is the dub repo checked out and intact?"
    )


def main() -> None:
    script = resolve_vendor_script()
    runpy.run_path(str(script), run_name="__main__")


__all__ = ["VENDOR_SCRIPT_NAME", "resolve_vendor_script", "main"]


if __name__ == "__main__":
    main()
