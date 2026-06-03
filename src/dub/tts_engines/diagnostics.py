"""dub.tts_engines.diagnostics — readiness probing for TTS backends.

These functions are the per-gate checks that ``dub doctor`` runs to
answer the operator's question: "why isn't route X working?". Each
check is independent so the doctor can print all gates and not just
the first one that fails.

A check never raises. It returns a (name, status, detail) triple where
status is one of: "ok" / "missing" / "warn" / "skipped". ``dub doctor``
maps these to a single overall "OK" or "MISSING" verdict.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


def which(name: str) -> tuple[str, str]:
    """Probe a binary on $PATH. Returns (status, detail)."""
    resolved = shutil.which(name)
    if resolved:
        return "ok", resolved
    return "missing", f"{name!r} not on $PATH"


def file_exists(path: Path) -> tuple[str, str]:
    if path.exists() and path.is_file():
        return "ok", str(path)
    return "missing", str(path)


def dir_exists(path: Path) -> tuple[str, str]:
    if path.exists() and path.is_dir():
        return "ok", str(path)
    return "missing", str(path)


def env_present(*names: str) -> tuple[str, str]:
    """Probe environment variables. Reports the first found name; if
    none are set, status is 'missing' and detail lists all candidates."""
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return "ok", f"{name}=<redacted, {len(val)} chars>"
    return "missing", ",".join(names)


def python_imports(module: str, *, interpreter: Optional[Path] = None) -> tuple[str, str]:
    """Probe whether a Python module is importable.

    If ``interpreter`` is None, uses ``sys.executable`` (the dub venv).
    If set, the check spawns a short subprocess to import the module
    under that interpreter — this is how we probe "is torch available
    in the OmniVoice venv?" without polluting the dub venv's imports.
    """
    if interpreter is None:
        try:
            importlib.import_module(module)
            return "ok", f"{module} importable in dub venv"
        except Exception as exc:  # ImportError, ModuleNotFoundError, etc.
            return "missing", f"{module} not importable: {type(exc).__name__}: {exc}"
    # Spawn a subprocess to probe the alternative interpreter
    try:
        result = subprocess.run(
            [str(interpreter), "-c", f"import {module}"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return "missing", f"interpreter probe failed: {type(exc).__name__}: {exc}"
    if result.returncode == 0:
        return "ok", f"{module} importable under {interpreter}"
    return "missing", f"{module} not importable under {interpreter}: {result.stderr.strip() or 'no stderr'}"


def tcp_connect(host: str, port: int, *, timeout: float = 1.5) -> tuple[str, str]:
    """Probe whether a TCP port is open. Used for local-inference
    services like the VoxCPM gradio server on 127.0.0.1:8808."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "ok", f"{host}:{port} reachable"
    except (OSError, socket.timeout) as exc:
        return "missing", f"{host}:{port} unreachable: {type(exc).__name__}: {exc}"


def resolve_interpreter(
    *,
    backend_preferred: Optional[Path],
    dub_executable: Optional[Path] = None,
) -> Path:
    """Pick which Python interpreter should run a TTS backend script.

    Strategy (in order):

    1. If ``backend_preferred`` is a usable file, use it. This is the
       legacy contract: operators point at the OmniVoice venv's
       ``python3``. We honor that during the migration window.
    2. Otherwise, fall back to ``dub_executable`` (``sys.executable`` by
       default). This is the new world: the dub venv has the backend
       installed via the optional extra.

    The result is always a path. If neither resolves to a real file,
    the caller should treat readiness as missing rather than crash;
    the returned path will simply not ``.exists()``.
    """
    dub_executable = dub_executable or Path(sys.executable)
    if backend_preferred is not None and Path(backend_preferred).exists():
        return Path(backend_preferred)
    return Path(dub_executable)


def aggregate(checks: Iterable[tuple[str, str, str]]) -> tuple[bool, str]:
    """Reduce a list of (name, status, detail) triples to a single
    (ok, one-liner) verdict. ``ok`` is True iff every status is "ok"
    or "skipped" (a "skipped" gate is not a failure, just a "we
    didn't probe this because earlier gates already failed")."""
    checks = list(checks)
    if not checks:
        return False, "no checks performed"
    failing = [c for c in checks if c[1] == "missing"]
    if failing:
        names = ", ".join(c[0] for c in failing)
        return False, f"missing: {names}"
    warned = [c for c in checks if c[1] == "warn"]
    if warned:
        names = ", ".join(c[0] for c in warned)
        return True, f"warn: {names}"
    return True, "all gates ok"


__all__ = [
    "which",
    "file_exists",
    "dir_exists",
    "env_present",
    "python_imports",
    "tcp_connect",
    "resolve_interpreter",
    "aggregate",
]
