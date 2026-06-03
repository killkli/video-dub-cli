"""dub.tts_engines.contract — interface that every TTS backend adapter must satisfy.

The contract is intentionally small. We are not asking each backend to
expose a Python-callable TTS API today — that is the R1 long-term
target. Today each backend is a *shelling-out* adapter: it points the
stage at the right script, the right interpreter, the right SRT flag.

Readiness is its own first-class concept because the operator's reality
is that the *adapter* ships in the repo, but the *backend* (heavy torch
stack, local gradio server) is opt-in via system bootstrap. ``dub doctor``
must be able to tell operators exactly which box is unchecked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol


@dataclass(frozen=True)
class TtsRoute:
    """Static metadata describing a TTS route. Pure data — no I/O.

    A route says: "if you want to speak ``source_lang`` lines, invoke
    ``script_name`` under the engines dir, and the per-line ref text
    is the original SRT, and the synthesized text is the translated
    SRT." It does NOT say where the script lives on disk, because that
    resolution happens at runtime by the backend's :meth:`build_route`
    factory.
    """
    source_lang: str           # "en", "ja", ...
    script_name: str           # "dubbing_batch_tts.py" (legacy) or
                               # "runner.py" (post-migration)
    source_srt_flag: str       # "--en-srt" or "--ja-srt"
    needs_project_dir: bool    # VoxCPM needs it; OmniVoice does not


@dataclass
class TtsReadiness:
    """Result of probing whether a backend is usable on the current host.

    ``ready`` is the aggregate verdict. ``checks`` is a list of named
    gates so ``dub doctor`` can show "wrapper: OK; interpreter: MISSING;
    deps: PARTIAL; service: SKIPPED" instead of a single boolean.

    ``detail`` is a free-form one-liner for the operator — it is what
    shows up in the doctor's per-backend line.
    """
    backend: str
    ready: bool
    detail: str
    checks: list[tuple[str, str, str]] = field(default_factory=list)
    # each check: (name, status, detail)
    # status is one of: "ok", "missing", "warn", "skipped"

    def to_doctor_line(self) -> str:
        status = "OK" if self.ready else "MISSING"
        return f"tts.{self.backend}: {status} ({self.detail})"


class TtsBackend(Protocol):
    """Structural type every backend adapter must implement.

    A backend module is expected to expose a top-level ``BACKEND`` object
    that conforms to this protocol, or to register itself via
    :func:`dub.tts_engines.register` at import time.
    """

    @property
    def name(self) -> str:
        """Stable identifier: 'omnivoice', 'voxcpme', 'edge', 'elevenlabs', ..."""
        ...

    def routes(self) -> list[TtsRoute]:
        """List every source-lang this backend can handle. Each route's
        metadata is static; the runtime is free to extend."""
        ...

    def build_route(self, config: object) -> "object":
        """Resolve the route for a specific config: pick the right
        script path, the right interpreter, the right interpreter
        overrides. Returns a :class:`dub.tts_engines.ResolvedRoute`."""
        ...

    def readiness(self, config: object) -> TtsReadiness:
        """Probe whether this backend is usable on the current host.
        Must be safe to call without side effects — it inspects files,
        does NOT shell out to invoke the actual TTS model."""
        ...


__all__ = ["TtsRoute", "TtsReadiness", "TtsBackend"]
