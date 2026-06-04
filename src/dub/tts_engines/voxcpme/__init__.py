"""dub.tts_engines.voxcpme — VoxCPM backend adapter.

Stage 5 shells to the repo-owned package runner at
``src/dub/tts_engines/voxcpme/runner.py`` (invokable as
``python -m dub.tts_engines.voxcpme``). That runner forwards CLI
argv unchanged to the vendored heavy-lift script
``vendor/pipeline_scripts/dubbing_batch_tts_vox.py``.

VoxCPM is the Japanese route (ja). Unlike OmniVoice, it has three
distinct readiness gates:

1. wrapper — the package runner exists in the engines dir
2. python deps — ``gradio_client`` (and ``opencc`` for t2s) must be
   importable. These come from the dub venv (not OmniVoice's venv),
   so we probe under ``sys.executable``.
3. service reachability — VoxCPM runs as a local gradio server
   (default 127.0.0.1:8808). If the server is down, the script
   cannot connect and the run will fail at the first cue.

The interpreter question is *not* a gate for VoxCPM: the gradio_client
and opencc packages are pip-installable into the dub venv itself
(via the ``[tts-vox]`` extra). So unlike OmniVoice, VoxCPM has no
"second Python interpreter" requirement.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dub.config import DubConfig
from dub.tts_engines import ResolvedRoute, register
from dub.tts_engines.contract import TtsReadiness, TtsRoute
from dub.tts_engines import diagnostics as diag


BACKEND_NAME = "voxcpme"

# VoxCPM is ja-only today. The * route would be a future enhancement
# (e.g. VoxCPM for en); the OmniVoice backend already covers the
# current * fallback, so leaving VoxCPM narrow is the safe move.
ROUTES: list[TtsRoute] = [
    TtsRoute(source_lang="ja", script_name="runner.py",
             source_srt_flag="--ja-srt", needs_project_dir=True),
]


def list_routes() -> list[TtsRoute]:
    return list(ROUTES)


def find_route(source_lang: str) -> Optional[TtsRoute]:
    for r in ROUTES:
        if r.source_lang == source_lang:
            return r
    return None


def engines_dir(config: DubConfig) -> Path:
    """Where the VoxCPM package-owned runner lives.

    Strictly the package directory containing ``runner.py``; we no
    longer fall back to a legacy ``skills_dir`` location for this
    adapter.
    """
    _ = config
    return Path(__file__).resolve().parent


def build_route(config: DubConfig, source_lang: str = "ja") -> ResolvedRoute:
    route = find_route(source_lang)
    if route is None:
        raise KeyError(f"VoxCPM has no route for source_lang={source_lang!r}")
    # Repo-owned entrypoint: the package runner in src/dub/tts_engines/
    # voxcpme/runner.py. The runner itself forwards argv to the
    # vendored heavy-lift script under vendor/pipeline_scripts/.
    script_path = engines_dir(config) / route.script_name
    # VoxCPM has no separate-interpreter requirement; it runs in the
    # dub venv (where gradio_client + opencc are installed via extras).
    interpreter = diag.resolve_interpreter(
        backend_preferred=None,
        dub_executable=Path(sys.executable),
    )
    return ResolvedRoute(
        script_path=script_path,
        source_srt_flag=route.source_srt_flag,
        needs_project_dir=route.needs_project_dir,
        interpreter=interpreter,
        backend_name=BACKEND_NAME,
    )


def readiness(config: DubConfig, *, service_host: str = "127.0.0.1",
              service_port: int = 8808) -> TtsReadiness:
    """Probe VoxCPM readiness. Five gates:

    1. wrapper — the package runner exists in the engines dir
    2. interpreter — the dub venv interpreter exists
    3. deps:gradio_client — gradio_client is importable
    4. deps:opencc — opencc is importable
    5. service — the local gradio server is reachable
    """
    checks: list[tuple[str, str, str]] = []

    route = find_route("ja")
    if route is None:
        return TtsReadiness(
            backend=BACKEND_NAME, ready=False,
            detail="no routes registered", checks=[],
        )

    script_path = engines_dir(config) / route.script_name
    checks.append(("wrapper", *diag.file_exists(script_path)))

    interp = Path(sys.executable)
    checks.append(("interpreter", "ok" if interp.exists() else "missing", str(interp)))

    # VoxCPM deps belong in the dub venv (not a separate interpreter),
    # so we probe under sys.executable — no subprocess needed.
    checks.append(("deps:gradio_client", *diag.python_imports("gradio_client")))
    checks.append(("deps:opencc", *diag.python_imports("opencc")))

    # Service reachability is reported but does NOT block readiness by
    # default — operators may want to start VoxCPM after seeing the
    # doctor's report. We mark it "warn" rather than "missing" so the
    # overall gate stays useful for "is the dub venv set up?".
    status, detail = diag.tcp_connect(service_host, service_port)
    if status == "ok":
        checks.append(("service", "ok", detail))
    else:
        checks.append((
            "service", "warn",
            f"{detail} (start VoxCPM server before running TTS)",
        ))

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
