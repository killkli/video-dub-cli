"""dub.tts_engines.omnivoice — OmniVoice backend adapter.

Stage 5 shells to the repo-owned package runner at
``src/dub/tts_engines/omnivoice/runner.py`` (invokable as
``python -m dub.tts_engines.omnivoice``). That runner forwards CLI
argv unchanged to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts.py``.

The adapter's job is to:

- declare the route contract (en, plus '*' catch-all for unknown
  source languages that fall back to OmniVoice)
- resolve the script path to the package runner (no more
  fall-through to a legacy ``skills_dir`` location)
- pick the right interpreter (OmniVoice's own venv with torch +
  omnivoice, or the dub venv as a fallback)
- report readiness so ``dub doctor`` can tell the operator what
  is missing

The actual heavy-lift script (``vendor/pipeline_scripts/dubbing_batch_tts.py``)
remains vendored because it has non-trivial atomic-write
contracts, ``--start/--end`` support, and per-cue error handling
that we do not want to re-implement here. R1 in
``docs/standalone-dependency-map.md`` captures the long-term
target of inlining it into the package, but that requires the
OmniVoice package to be importable from the dub venv — which is
not a wave-12 deliverable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dub.config import DubConfig
from dub.tts_engines import ResolvedRoute, register
from dub.tts_engines.contract import TtsReadiness, TtsRoute
from dub.tts_engines import diagnostics as diag


BACKEND_NAME = "omnivoice"

# The package-owned runner is the canonical invocation target for
# this backend. Stage 5 always shells to ``runner.py``; that runner
# forwards to the vendored script in ``vendor/pipeline_scripts/``.
ROUTES: list[TtsRoute] = [
    TtsRoute(source_lang="en", script_name="runner.py",
             source_srt_flag="--en-srt", needs_project_dir=False),
    TtsRoute(source_lang="*", script_name="runner.py",
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
    """Where the OmniVoice package-owned runner lives.

    This is now strictly the package directory containing
    ``runner.py``; we no longer fall back to a legacy
    ``skills_dir`` location for this adapter.
    """
    _ = config
    return Path(__file__).resolve().parent


def build_route(config: DubConfig, source_lang: str = "en") -> ResolvedRoute:
    route = find_route(source_lang)
    if route is None:
        raise KeyError(f"OmniVoice has no route for source_lang={source_lang!r}")
    # Repo-owned entrypoint: the package runner in src/dub/tts_engines/
    # omnivoice/runner.py. The runner itself forwards argv to the
    # vendored heavy-lift script under vendor/pipeline_scripts/.
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
    """Probe OmniVoice readiness. Five gates:

    1. wrapper — the package runner exists in the engines dir
    2. interpreter — the OmniVoice Python interpreter (or the dub
       venv as a fallback) exists and runs
    3. env:DUB_OMNIVOICE_ROOT — the env var pointing at the OmniVoice
       dev repo checkout is set and points at a real checkout
       (the ``omnivoice`` package is not on PyPI, so operators
       clone the dev repo and point the env var at it). This is
       the only operator-supplied coupling the repo requires;
       everything else flows through the package runner.
    4. deps — torch is importable under that interpreter
    5. model — we deliberately don't probe model cache here; that's
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

    # Env-var gate: DUB_OMNIVOICE_ROOT (or legacy OMNIVOICE_ROOT)
    # must point at a real OmniVoice checkout. This is the single
    # operator-supplied coupling that is unavoidable today (the
    # omnivoice package is not on PyPI). Report it as a first-class
    # gate so operators see "missing env" instead of a confusing
    # import error from the script itself.
    omni_root = os.environ.get("DUB_OMNIVOICE_ROOT") or os.environ.get("OMNIVOICE_ROOT")
    if not omni_root:
        checks.append((
            "env:DUB_OMNIVOICE_ROOT", "missing",
            "DUB_OMNIVOICE_ROOT is not set; export it to point at "
            "the OmniVoice dev repo checkout (the package is not on "
            "PyPI yet). See `dub bootstrap`.",
        ))
    else:
        root_path = Path(omni_root).expanduser().resolve()
        marker = root_path / "omnivoice" / "models" / "omnivoice.py"
        if marker.is_file():
            checks.append(("env:DUB_OMNIVOICE_ROOT", "ok", str(root_path)))
        else:
            checks.append((
                "env:DUB_OMNIVOICE_ROOT", "missing",
                f"DUB_OMNIVOICE_ROOT={root_path} does not look like a "
                f"valid OmniVoice checkout (missing {marker}).",
            ))

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
