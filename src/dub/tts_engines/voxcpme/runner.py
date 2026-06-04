#!/usr/bin/env python3
"""Package-owned VoxCPM Stage-05 runner.

This keeps the execution entrypoint inside the repo package while we still
reuse the proven heavy-lift implementation in vendor/pipeline_scripts.
The wrapper is intentionally dependency-light so it can run under the dub
venv and forward argv unchanged.
"""

from __future__ import annotations

import runpy
from pathlib import Path


VENDOR_SCRIPT = Path(__file__).resolve().parents[4] / "vendor" / "pipeline_scripts" / "dubbing_batch_tts_vox.py"


def main() -> None:
    runpy.run_path(str(VENDOR_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
