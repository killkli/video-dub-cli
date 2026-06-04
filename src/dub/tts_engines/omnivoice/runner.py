#!/usr/bin/env python3
"""Package-owned OmniVoice Stage-05 runner.

This keeps the execution entrypoint inside the repo package while we
still reuse the proven heavy-lift implementation in
``vendor/pipeline_scripts/dubbing_batch_tts.py``. The wrapper is
intentionally dependency-light so it can run under the dub venv
and forward argv unchanged.

The runner is invoked two ways:

- by the active Stage 5 code in ``dub.stages.tts`` (which resolves
  it through the OmniVoice adapter's :func:`build_route`).
- by a fresh operator via ``python -m dub.tts_engines.omnivoice``.

Both paths land here. The vendored script is resolved at call time
(walking up from this file until a ``vendor/pipeline_scripts/``
directory is visible) so that a missing script fails with a clear
runtime error instead of breaking ``dub`` import. Operators in
pip-install layouts (where ``dub`` lives under ``site-packages``)
get the same behaviour: we walk up from the package's installed
location, which is the same module path but a different prefix.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path


VENDOR_SCRIPT_NAME = "dubbing_batch_tts.py"


def resolve_vendor_script() -> Path:
    """Locate the heavy-lift Stage-05 script.

    Production defaults to the repo-owned vendored script under
    ``vendor/pipeline_scripts/``. Hermetic integration / operator QA may
    override that location via ``DUB_PIPELINE_SCRIPTS_DIR``. Keep this
    runner dependency-light: it may be executed by a backend interpreter
    that does not have the ``dub`` package importable.
    """
    override = os.environ.get("DUB_PIPELINE_SCRIPTS_DIR")
    if override:
        candidate = Path(override) / VENDOR_SCRIPT_NAME
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(
            f"Could not locate TTS script {VENDOR_SCRIPT_NAME!r} at {candidate}. "
            "DUB_PIPELINE_SCRIPTS_DIR override is broken."
        )

    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "vendor" / "pipeline_scripts" / VENDOR_SCRIPT_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate TTS script {VENDOR_SCRIPT_NAME!r} walking up from {here}. "
        "Repo layout invariant broken."
    )


def main() -> None:
    script = resolve_vendor_script()
    runpy.run_path(str(script), run_name="__main__")


__all__ = ["VENDOR_SCRIPT_NAME", "resolve_vendor_script", "main"]


if __name__ == "__main__":
    main()
