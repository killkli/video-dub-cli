"""dub.tts_engines — repo-owned TTS backend adapter registry.

The runtime's TTS stage (Stage 5 in `dub.stages.tts`) used to point at
external skill scripts under ``~/.hermes/skills/media/video-dubbing-pipeline/scripts``.
This package is the consolidation step: the repo now owns the *adapter*
contract — which script a route resolves to, which interpreter flag
it expects, whether it needs a project dir, and what readiness signals
``dub doctor`` should report.

The actual heavy-lift TTS scripts (OmniVoice / VoxCPM batch invokers)
are still kept in the legacy location during the migration window. The
adapter does not re-vendor them wholesale; it instead resolves them
through the new ``paths.tts_engines_dir`` config field (defaulting to
the legacy ``paths.skills_dir`` if the operator has not migrated) and
exposes a uniform readiness contract.

Long-term target: the scripts themselves become proper Python modules
under ``dub.tts_engines.omnivoice.runner`` and ``dub.tts_engines.voxcpme.runner``
and the stage invokes ``python -m dub.tts_engines.omnivoice`` directly,
killing the legacy skills_dir. R1 in docs/standalone-dependency-map.md
captures that follow-up. This module ships the adapter surface that
makes that migration an in-place change to the engine modules without
touching the stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Optional

# Public re-exports — the stage module imports these names.
from dub.tts_engines.contract import (  # noqa: E402, F401
    TtsBackend,
    TtsReadiness,
    TtsRoute,
)


def _autoregister_builtin_backends() -> None:
    """Import built-in backend modules for their register() side effects."""
    for mod in (
        "dub.tts_engines.omnivoice",
        "dub.tts_engines.voxcpme",
    ):
        import_module(mod)


@dataclass(frozen=True)
class ResolvedRoute:
    """What the stage needs to actually shell out: which script, which
    source-SRT flag, and which interpreter path to use.

    ``script_path`` is repo-owned via the new ``paths.tts_engines_dir`` config
    field, falling back to ``paths.skills_dir`` for operators who have not
    migrated their config yet. ``interpreter`` is the Python interpreter
    that hosts the backend's deps (the OmniVoice venv or the dub venv
    itself, depending on what is available — see
    :func:`dub.tts_engines.diagnostics.resolve_interpreter`).
    """
    script_path: Path
    source_srt_flag: str
    needs_project_dir: bool
    interpreter: Path
    backend_name: str  # "omnivoice" or "voxcpme"


# Registry: backend name → factory that builds the route for a given config.
# Adding a new backend means: drop a module in src/dub/tts_engines/<name>/
# that implements ``build_route(config) -> ResolvedRoute`` and append it here.
# We type the factory as ``Callable[..., ResolvedRoute]`` so backend modules
# can pass in concrete (DubConfig) → ResolvedRoute factories without
# contravariance friction.
_REGISTRY: dict[str, Callable[..., ResolvedRoute]] = {}


def register(backend_name: str, factory: Callable[..., ResolvedRoute]) -> None:
    """Register a backend factory. Used by the engine submodules; not
    intended as a public API for end users."""
    _REGISTRY[backend_name] = factory


def get_factory(backend_name: str) -> Callable[..., ResolvedRoute]:
    if backend_name not in _REGISTRY:
        raise KeyError(
            f"unknown TTS backend: {backend_name!r}; "
            f"registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[backend_name]


def list_registered() -> list[str]:
    """Names of every backend that has called :func:`register` so far."""
    return sorted(_REGISTRY)


def engines_dir() -> Path:
    """Canonical repo-owned TTS runtime script directory.

    Operators no longer need to configure ``tts_engines_dir``. Stage 5
    resolves the runtime wrappers from this repo's vendored pipeline
    scripts directly.

    We intentionally return ``vendor/pipeline_scripts`` rather than the
    package directory itself because the heavy-lift wrapper scripts still
    live there during the migration window.
    """
    pkg_dir = Path(str(resources.files("dub.tts_engines")))
    repo_root = pkg_dir.parents[2]
    return repo_root / "vendor" / "pipeline_scripts"


def builtin_backends() -> list[str]:
    """Names of all built-in backends, regardless of readiness. Operators
    can list every supported engine even if none of them is currently
    usable on this host."""
    return sorted(_REGISTRY)


_autoregister_builtin_backends()


__all__ = [
    "TtsBackend",
    "TtsReadiness",
    "TtsRoute",
    "ResolvedRoute",
    "engines_dir",
    "get_factory",
    "register",
    "list_registered",
    "builtin_backends",
]
