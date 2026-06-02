"""dub.bootstrap — standalone `dub-bootstrap` script entrypoint.

`uv run dub-bootstrap` should behave identically to `uv run dub bootstrap`.
The bootstrap guidance logic lives in `dub.cli.bootstrap`; this module
forwards to the main CLI group with the right sub-command, so the
standalone script entrypoint declared in `pyproject.toml [project.scripts]`
resolves to a real, working command.
"""
from __future__ import annotations

from dub.cli import main as _cli_main


def main() -> None:
    """Invoke `dub bootstrap` as if invoked from a shell."""
    _cli_main(["bootstrap"], standalone_mode=True)


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    main()
