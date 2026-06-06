"""dub.tts_engines.stems — stem-separation backend adapter.

This is NOT a TTS engine — it is the preprocessing stage that runs
before ASR to isolate the vocal stem. It follows the same readiness()
pattern as the TTS backends so ``dub doctor`` can probe it uniformly.

The actual separation is performed by the vendored ``vocal_remover``
package (src/vocal_remover/) invoked as a module:

    stems_python -m vocal_remover --stems vocals <video>

Bootstrap contract (mirrors omnivoice / voxcpme):
    1. ``uv sync --extra stems``          installs demucs-mlx + tqdm
    2. ``uv run dub bootstrap-stems``      creates dedicated venv + wires config
    3. ``uv run dub doctor``              verifies all gates
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dub.config import DubConfig
from dub.tts_engines.contract import TtsReadiness
from dub.tts_engines import diagnostics as diag


BACKEND_NAME = "stems"

# The stems backend is a preprocessing step, not a TTS route.
# There is no source_lang routing — any video can be stemmed.
ROUTES: list = []  # not applicable for this backend


def readiness(config: DubConfig) -> TtsReadiness:
    """Probe stems backend readiness. Three gates:

    1. wrapper — the vendored vocal_remover CLI module exists
    2. interpreter — stems_python (or dub venv fallback) runs
    3. deps:* — every import gate the vendored runtime needs is importable

    Model weights are deliberately not probed here; that's a bootstrap
    / first-run download concern, not a doctor gate.
    """
    checks: list[tuple[str, str, str]] = []
    runtime_imports = ("demucs_mlx", "tqdm")

    # Gate 1: wrapper — can we invoke `python -m vocal_remover`?
    # The module lives under src/vocal_remover/ in this repo.
    repo_root = Path(__file__).resolve().parents[4]
    vocal_remover_module = repo_root / "src" / "vocal_remover" / "__main__.py"
    checks.append(("wrapper", *diag.file_exists(vocal_remover_module)))

    # Gate 2: interpreter — resolve stems_python or fall back to dub venv
    interp = Path(config.paths.stems_python)
    if interp.exists():
        checks.append(("interpreter", "ok", str(interp)))
    else:
        fallback = Path(sys.executable)
        checks.append((
            "interpreter", "warn",
            f"{interp} missing; would fall back to dub venv {fallback} "
            f"(demucs-mlx deps must be installed there)",
        ))
        interp = fallback

    # Gate 3: the vendored runtime's Python imports are available under
    # the chosen interpreter. Keep this in sync with src/vocal_remover/cli.py.
    if interp.exists():
        for module_name in runtime_imports:
            checks.append((f"deps:{module_name}", *diag.python_imports(module_name, interpreter=interp)))
    else:
        for module_name in runtime_imports:
            checks.append((f"deps:{module_name}", "skipped", "no interpreter; can't probe"))

    ready, detail = diag.aggregate(checks)
    return TtsReadiness(
        backend=BACKEND_NAME, ready=ready, detail=detail, checks=checks,
    )


def build_route(config: DubConfig, source_lang: str = "*") -> object:
    """Build a resolved route — returns the stems interpreter + module path."""
    interp = diag.resolve_interpreter(
        backend_preferred=Path(config.paths.stems_python),
        dub_executable=Path(sys.executable),
    )
    repo_root = Path(__file__).resolve().parents[4]
    module_path = repo_root / "src" / "vocal_remover" / "__main__.py"
    return {
        "interpreter": interp,
        "module": "vocal_remover",
        "script_path": module_path,
    }


def find_route(source_lang: str) -> Optional[object]:
    """Stems has no language routing."""
    return None


# No auto-registration — stems is not a TTS route.
# It is probed independently by `dub doctor`.


__all__ = [
    "BACKEND_NAME",
    "ROUTES",
    "readiness",
    "build_route",
    "find_route",
]