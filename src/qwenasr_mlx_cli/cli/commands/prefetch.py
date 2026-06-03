"""
prefetch command — download and cache the default MLX model with progress output.
Verifies cache completeness before declaring success.
"""
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, MofNCompleteColumn

from qwenasr_mlx_cli.backends.registry import BackendRegistry
from qwenasr_mlx_cli.core.exceptions import BackendUnavailableError

# Matches the model id hardcoded in MLXBackend so we can audit the cache directly
_MODEL_ID = "mlx-community/Qwen3-ASR-1.7B-bf16"
_HF_CACHE_ROOT = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
_CACHE_ROOT = Path(_HF_CACHE_ROOT) / "hub"
_MODEL_CACHE = _CACHE_ROOT / f"models--{_MODEL_ID.replace('/', '--')}"

# Files that must exist in the resolved snapshot for a complete cache
_REQUIRED_SNAPSHOT_FILES = {
    ".gitattributes",
    "README.md",
    "chat_template.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors",
    "model.safetensors.index.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
}


def _check_incomplete_blobs() -> list[Path]:
    """Return any .incomplete blob files still sitting in the cache."""
    blobs_dir = _MODEL_CACHE / "blobs"
    if not blobs_dir.exists():
        return []
    return list(blobs_dir.glob("*.incomplete"))


def _resolve_snapshot() -> Path | None:
    """Return the resolved snapshot directory or None if not yet downloaded."""
    snapshots_dir = _MODEL_CACHE / "snapshots"
    if not snapshots_dir.exists():
        return None
    for sub in snapshots_dir.iterdir():
        if sub.is_dir():
            return sub
    return None


def _audit_cache() -> dict:
    """Run cache completeness checks, return a dict of findings."""
    findings: dict = {
        "cache_root": str(_MODEL_CACHE),
        "incomplete_blobs": [],
        "snapshot_resolved": False,
        "missing_files": set(),
        "all_present": False,
    }

    findings["incomplete_blobs"] = [str(p) for p in _check_incomplete_blobs()]

    snapshot = _resolve_snapshot()
    if snapshot is not None:
        findings["snapshot_resolved"] = True
        findings["snapshot_path"] = str(snapshot)
        actual = {p.name for p in snapshot.iterdir()}
        findings["missing_files"] = _REQUIRED_SNAPSHOT_FILES - actual
    else:
        findings["snapshot_resolved"] = False
        findings["missing_files"] = _REQUIRED_SNAPSHOT_FILES

    findings["all_present"] = (
        findings["snapshot_resolved"]
        and not findings["incomplete_blobs"]
        and not findings["missing_files"]
    )
    return findings


def prefetch_command() -> None:
    """
    Prefetch the default MLX ASR model to the local cache.

    Downloads the model from HuggingFace Hub if not already cached,
    then verifies cache completeness: no .incomplete blobs, all required
    model files present, and the resolved snapshot path printed.
    """
    console = Console()

    # Quick availability check first
    registry = BackendRegistry()
    try:
        backend = registry.create("mlx")
    except BackendUnavailableError:
        console.print("[red]MLX backend is not available. Install with: pip install qwenasr-mlx-cli[mlx][/red]")
        raise typer.Exit(code=1)

    if not backend.available():
        console.print("[red]MLX backend optional dependency not installed: pip install qwenasr-mlx-cli[mlx][/red]")
        raise typer.Exit(code=1)

    console.print(f"[dim]Model: {_MODEL_ID}[/dim]")
    console.print(f"[dim]Cache: {_MODEL_CACHE}[/dim]")

    # Run audit before triggering download — if already complete, skip re-download
    before = _audit_cache()
    if before["all_present"]:
        console.print("[green]✓ Cache complete — no download needed.[/green]")
        console.print(f"  snapshot: {before.get('snapshot_path', 'n/a')}")
        raise typer.Exit(code=0)

    console.print("\n[dim]Downloading model (first run may take several minutes)...[/dim]\n")

    # Trigger eager load via _ensure_model — this is the existing load path reused
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Fetching model files", total=None)

        try:
            backend._ensure_model()  # type: ignore[access-private]
        except Exception as exc:
            progress.stop()
            console.print(f"[red]Download failed: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    # Post-download audit
    after = _audit_cache()

    if after["incomplete_blobs"]:
        console.print(f"[red]✗ {len(after['incomplete_blobs'])} incomplete blob(s) found:[/red]")
        for b in after["incomplete_blobs"]:
            console.print(f"  {b}")
        raise typer.Exit(code=1)

    if not after["snapshot_resolved"]:
        console.print("[red]✗ Snapshot not resolved after download.[/red]")
        raise typer.Exit(code=1)

    if after["missing_files"]:
        console.print(f"[red]✗ {len(after['missing_files'])} file(s) missing:[/red]")
        for f in sorted(after["missing_files"]):
            console.print(f"  {f}")
        raise typer.Exit(code=1)

    console.print(f"\n[green]✓ Model cached successfully.[/green]")
    console.print(f"  snapshot: {after.get('snapshot_path', 'n/a')}")
    console.print(f"  cache:    {_MODEL_CACHE}")
    raise typer.Exit(code=0)