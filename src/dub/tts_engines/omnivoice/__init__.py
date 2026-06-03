"""dub.tts_engines.omnivoice — OmniVoice backend adapter.

Status: legacy-shellout adapter. The actual heavy-lift TTS script still
lives in this repo's ``vendor/pipeline_scripts/dubbing_batch_tts.py``,
not in this package.
The adapter's job is to:

- declare the route contract (en / ja-also-falls-back-to-OmniVoice)
- pick the right script under the engines dir
- pick the right interpreter (OmniVoice's own venv with torch + omnivoice)
- report readiness so ``dub doctor`` can tell the operator what is missing

Long-term target (R1 in docs/standalone-dependency-map.md): the script
becomes ``dub.tts_engines.omnivoice.runner`` and is invoked in-process
from the dub venv. This module's interface stays the same — the
``build_route`` impl just changes its interpreter-resolution and
script-resolution internals.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dub.config import DubConfig
from dub.tts_engines import ResolvedRoute, engines_dir as builtin_engines_dir, register
from dub.tts_engines.contract import TtsReadiness, TtsRoute
from dub.tts_engines import diagnostics as diag


BACKEND_NAME = "omnivoice"

# Two scripts under the engines dir match this backend's routes today:
#   - dubbing_batch_tts.py   (en route, OmniVoice MPS backend)
# The same script is used for the ja-fallback if the VoxCPM backend is
# not installed; we let the route resolver prefer VoxCPM first via the
# ``tts_engines`` registry order in the stage.
ROUTES: list[TtsRoute] = [
    TtsRoute(source_lang="en", script_name="dubbing_batch_tts.py",
             source_srt_flag="--en-srt", needs_project_dir=False),
    TtsRoute(source_lang="*", script_name="dubbing_batch_tts.py",
             source_srt_flag="--en-srt", needs_project_dir=False),
]


def list_routes() -> list[TtsRoute]:
    return list(ROUTES)


def find_route(source_lang: str) -> Optional[TtsRoute]:
    for r in ROUTES:
        if r.source_lang == source_lang:
            return r
    for r in ROUTES:
        if r.source_lang == "*":
            return r
    return None


def engines_dir(config: DubConfig) -> Path:
    """Where the OmniVoice runtime wrapper lives.

    The wrapper is now repo-owned and resolved from the installed checkout.
    ``config`` is kept for signature compatibility with the backend
    registry, but operators no longer need to point at a custom scripts dir.
    """
    _ = config
    return builtin_engines_dir()


def build_route(config: DubConfig, source_lang: str = "en") -> ResolvedRoute:
    route = find_route(source_lang)
    if route is None:
        raise KeyError(f"OmniVoice has no route for source_lang={source_lang!r}")
    script_path = engines_dir(config) / route.script_name
    interpreter = diag.resolve_interpreter(
        backend_preferred=Path(config.paths.omnivoice_python),
        dub_executable=Path(sys.executable),
    )
    return ResolvedRoute(
        script_path=script_path,
        source_srt_flag=route.source_srt_flag,
        needs_project_dir=route.needs_project_dir,
        interpreter=interpreter,
        backend_name=BACKEND_NAME,
    )


def readiness(config: DubConfig) -> TtsReadiness:
    """Probe OmniVoice readiness. Four gates:

    1. wrapper — the script exists in the engines dir
    2. interpreter — the OmniVoice Python interpreter exists and runs
    3. deps — torch (and ideally omnivoice) is importable under that interpreter
    4. model — we deliberately don't probe model cache here; that's
       a bootstrap step, not a doctor gate.

    Skipped gates (e.g. deps when interpreter is missing) are reported
    as ``skipped`` rather than ``missing`` so the operator can see
    which boxes we never got to.
    """
    checks: list[tuple[str, str, str]] = []

    route = find_route("en")
    if route is None:
        return TtsReadiness(
            backend=BACKEND_NAME, ready=False,
            detail="no routes registered", checks=[],
        )
    script_path = engines_dir(config) / route.script_name
    checks.append(("wrapper", *diag.file_exists(script_path)))

    interp = Path(config.paths.omnivoice_python)
    if interp.exists():
        checks.append(("interpreter", "ok", str(interp)))
    else:
        # Fall back to dub venv interpreter: still a valid gate, but
        # we mark it warn because OmniVoice needs torch in that venv.
        fallback = Path(sys.executable)
        checks.append((
            "interpreter", "warn",
            f"{interp} missing; would fall back to dub venv {fallback} "
            f"(OmniVoice's torch deps must be installed there)",
        ))
        interp = fallback

    # Probe torch under the chosen interpreter. omnivoice itself may
    # not be on PyPI yet, so we do not require it as a hard gate —
    # the actual error surfaces when the script runs. The doc tells
    # the operator how to satisfy it.
    if interp.exists():
        checks.append(("deps:torch", *diag.python_imports("torch", interpreter=interp)))
        # omni-cli is the OmniVoice CLI; if it's a real package, the
        # operator can verify it via `python -c "import omni_cli"`.
        # We mark as 'skipped' if torch is missing to avoid noisy
        # double-failures.
        torch_status = checks[-1][1]
        if torch_status == "ok":
            checks.append(("deps:omnivoice", *diag.python_imports("omnivoice", interpreter=interp)))
        else:
            checks.append(("deps:omnivoice", "skipped", "torch missing; can't probe omnivoice"))
    else:
        checks.append(("deps:torch", "skipped", "no interpreter; can't probe"))
        checks.append(("deps:omnivoice", "skipped", "no interpreter; can't probe"))

    ready, detail = diag.aggregate(checks)
    return TtsReadiness(
        backend=BACKEND_NAME, ready=ready, detail=detail, checks=checks,
    )


# Auto-register on import. The stage module looks up backends by name.
def _build(config: DubConfig) -> ResolvedRoute:
    return build_route(config)


register(BACKEND_NAME, _build)


__all__ = [
    "BACKEND_NAME",
    "ROUTES",
    "list_routes",
    "find_route",
    "build_route",
    "readiness",
    "engines_dir",
]
