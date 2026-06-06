from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from demucs_mlx import Separator

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover
    tqdm = None

try:
    from demucs_mlx import Separator
except ImportError:  # pragma: no cover
    Separator = None  # type: ignore[assignment]

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
STEMS = ("vocals", "drums", "bass", "other")
DEFAULT_MODEL = "htdemucs"
MODEL_ALIASES = {
    "htdemucs_nano": "htdemucs",
    "htdemucs_full": "htdemucs_ft",
}


class SeparationError(RuntimeError):
    pass


def parse_stems(value: str) -> list[str]:
    normalized = value.strip().lower()
    if not normalized:
        raise SeparationError("--stems cannot be empty")
    if normalized == "all":
        return list(STEMS)

    requested: list[str] = []
    seen: set[str] = set()
    for item in normalized.split(","):
        stem = item.strip()
        if not stem:
            continue
        if stem not in STEMS:
            raise SeparationError(
                f"Unsupported stem '{stem}'. Supported: {', '.join(STEMS)} or 'all'"
            )
        if stem not in seen:
            requested.append(stem)
            seen.add(stem)

    if not requested:
        raise SeparationError("--stems must name at least one supported stem")
    return requested


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vocal-remover",
        description="Separate vocals and instrument stems with MLX-accelerated demucs-mlx on Apple Silicon.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input media path(s).",
    )
    parser.add_argument(
        "--input",
        dest="input_paths",
        action="append",
        default=[],
        help="Legacy input flag. Repeat --input for batch processing.",
    )
    parser.add_argument(
        "--output",
        dest="output",
        help=(
            "Output file or directory. Single-input single-stem mode accepts a file path. "
            "Otherwise provide a directory; defaults to writing stem WAVs next to each input."
        ),
    )
    parser.add_argument(
        "--stems",
        default="vocals",
        help="Comma-separated stems to export (vocals,drums,bass,other) or 'all'. Default: vocals",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "demucs-mlx model name (default: htdemucs). "
            "Task aliases: htdemucs_nano -> htdemucs, htdemucs_full -> htdemucs_ft"
        ),
    )
    parser.add_argument("--shifts", type=int, default=1, help="Number of random shifts for demucs-mlx")
    parser.add_argument("--overlap", type=float, default=0.25, help="Chunk overlap ratio")
    parser.add_argument("--batch-size", type=int, default=8, help="Inference batch size")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed for deterministic shifts")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Path to ffmpeg binary")
    parser.add_argument("--ffprobe", default="ffprobe", help="Path to ffprobe binary")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary WAV intermediates for debugging")
    parser.add_argument("--verbose", action="store_true", help="Print ffmpeg commands and extra details")
    return parser


def combine_inputs(args: argparse.Namespace) -> list[str]:
    inputs = list(args.inputs or [])
    inputs.extend(args.input_paths or [])
    if not inputs:
        raise SeparationError("At least one input path is required")
    return inputs


def require_backend_installed() -> None:
    if Separator is None or tqdm is None:
        raise SeparationError(
            "Project dependencies are not installed in this Python environment (missing demucs-mlx and/or tqdm). "
            "Install project dependencies first, e.g. 'uv sync --extra stems' or 'uv run dub bootstrap-stems'."
        )


def resolve_model_name(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        raise SeparationError("--model cannot be empty")
    return MODEL_ALIASES.get(normalized.lower(), normalized)


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise SeparationError(f"Required binary not found on PATH: {name}")


def ensure_input(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise SeparationError(f"Input does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SeparationError(
            f"Unsupported input extension for {path.name}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return path


def default_stem_output_path(input_path: Path, stem: str) -> Path:
    return input_path.with_name(f"{input_path.stem}.{stem}.wav")


def resolve_stem_output_paths(
    input_path: Path,
    requested_output: str | None,
    stems: list[str],
    multi_input: bool,
) -> dict[str, Path]:
    if not requested_output:
        return {stem: default_stem_output_path(input_path, stem) for stem in stems}

    output = Path(requested_output).expanduser()
    single_file_mode = len(stems) == 1 and not multi_input and output.suffix.lower() == ".wav"
    if single_file_mode:
        output.parent.mkdir(parents=True, exist_ok=True)
        return {stems[0]: output.resolve()}

    if output.suffix:
        raise SeparationError(
            "Explicit output file paths are only supported for single-input single-stem mode; otherwise use a directory"
        )

    output.mkdir(parents=True, exist_ok=True)
    return {stem: (output / f"{input_path.stem}.{stem}.wav").resolve() for stem in stems}


def run_command(command: list[str], verbose: bool = False) -> None:
    if verbose:
        print("$", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def decode_to_wav(input_path: Path, wav_path: Path, ffmpeg: str, verbose: bool = False) -> None:
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    run_command(command, verbose=verbose)


def export_stem_wav(stem_audio: Any, output_path: Path, samplerate: int, verbose: bool = False) -> None:
    import numpy as np

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"Writing {output_path}", flush=True)

    audio = np.asarray(stem_audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[None, :]
    if audio.ndim != 2:
        raise SeparationError(f"Expected stem audio with 1 or 2 dimensions, got shape {audio.shape}")

    peak = float(np.max(np.abs(audio), initial=0.0))
    if peak > 1.0:
        audio = audio / max(1.01 * peak, 1.0)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = np.rint(audio.T * 32767.0).astype("<i2")

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(int(audio.shape[0]))
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(samplerate))
        wav_file.writeframes(pcm.tobytes())


def load_decoded_wav(decoded_wav: Path) -> Any:
    import numpy as np

    with wave.open(str(decoded_wav), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()
        if wav_file.getcomptype() != "NONE":
            raise SeparationError(f"Unsupported WAV compression: {wav_file.getcomptype()}")
        frames = wav_file.readframes(frame_count)

    sample_formats = {
        2: (np.int16, 32768.0),
        4: (np.int32, 2147483648.0),
    }
    sample_format = sample_formats.get(sample_width)
    if sample_format is None:
        raise SeparationError(f"Unsupported WAV sample width: {sample_width}")

    dtype, scale = sample_format
    audio = np.frombuffer(frames, dtype=dtype)
    expected_size = frame_count * channels
    if audio.size != expected_size:
        raise SeparationError(
            f"Decoded WAV frame count mismatch: expected {expected_size} samples, got {audio.size}"
        )
    return audio.reshape(frame_count, channels).T.astype(np.float32) / scale


def separate_audio_with_fallback(separator: Separator, decoded_wav: Path) -> dict[str, Any]:
    try:
        _, stems = separator.separate_audio_file(str(decoded_wav))
        return stems
    except TypeError as exc:
        if "Unable to convert function return value to a Python type" not in str(exc):
            raise
        _, stems = separator.separate_tensor(load_decoded_wav(decoded_wav))
        return stems


def separate_file(
    input_path: Path,
    output_paths: dict[str, Path],
    separator: Separator,
    ffmpeg: str,
    keep_temp: bool,
    verbose: bool,
) -> dict[str, Path]:
    with tempfile.TemporaryDirectory(prefix="vocal-remover-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        decoded_wav = tmpdir_path / f"{input_path.stem}.decoded.wav"

        decode_to_wav(input_path, decoded_wav, ffmpeg=ffmpeg, verbose=verbose)
        if verbose:
            print(f"Running separation for {input_path.name}", flush=True)
        stems = separate_audio_with_fallback(separator, decoded_wav)

        missing = [stem for stem in output_paths if stem not in stems]
        if missing:
            raise SeparationError(
                f"demucs-mlx did not return requested stem(s): {', '.join(missing)}"
            )

        written: dict[str, Path] = {}
        for stem_name, output_path in output_paths.items():
            print(f"[{input_path.name}] exporting stem: {stem_name}", flush=True)
            export_stem_wav(stems[stem_name], output_path, samplerate=separator.samplerate, verbose=verbose)
            written[stem_name] = output_path
            if keep_temp:
                kept_path = output_path.with_suffix(output_path.suffix + ".tmp.wav")
                shutil.copy2(output_path, kept_path)
                print(f"Kept intermediate WAV at {kept_path}")
        return written


def process_files(inputs: Iterable[Path], args: argparse.Namespace) -> list[Path]:
    inputs = list(inputs)
    requested_stems = parse_stems(args.stems)
    require_backend_installed()
    resolved_model = resolve_model_name(args.model)
    try:
        assert Separator is not None
        assert tqdm is not None
        separator = Separator(
            model=resolved_model,
            shifts=args.shifts,
            overlap=args.overlap,
            batch_size=args.batch_size,
            seed=args.seed,
            progress=len(inputs) == 1,
        )
    except ValueError as exc:
        raise SeparationError(str(exc)) from exc
    multi_input = len(inputs) > 1
    outputs: list[Path] = []

    with tqdm(inputs, unit="file", desc="Separating stems") as progress:
        for input_path in progress:
            progress.set_postfix(current=input_path.name)
            output_paths = resolve_stem_output_paths(
                input_path,
                args.output,
                requested_stems,
                multi_input=multi_input,
            )
            written = separate_file(
                input_path=input_path,
                output_paths=output_paths,
                separator=separator,
                ffmpeg=args.ffmpeg,
                keep_temp=args.keep_temp,
                verbose=args.verbose,
            )
            for stem_name in requested_stems:
                result_path = written[stem_name]
                outputs.append(result_path)
                tqdm.write(f"Created {result_path}")
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        require_binary(args.ffmpeg)
        require_binary(args.ffprobe)
        inputs = [ensure_input(path_str) for path_str in combine_inputs(args)]
        outputs = process_files(inputs, args)
        print("Done:")
        for output in outputs:
            print(output)
        return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode or 1
    except SeparationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())