from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from qwenasr_mlx_cli.core.exceptions import (
    ASRProcessingError,
    BackendUnavailableError,
)
from qwenasr_mlx_cli.core.types import TranscriptionRequest, TranscriptionResult

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


class MLXBackend:
    name = "mlx"
    _model_id = "mlx-community/Qwen3-ASR-1.7B-bf16"
    _warmmed_up = False

    def __init__(self) -> None:
        self._import_error: str | None = None
        self._model: object | None = None
        try:
            from qwen3_asr_mlx import Qwen3ASR  # type: ignore[import]  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on optional install
            self._import_error = str(exc)

    def available(self) -> bool:
        return self._import_error is None

    def _cached_snapshot_path(self) -> Path | None:
        cache_root = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
        model_cache = cache_root / "hub" / f"models--{self._model_id.replace('/', '--')}"
        blobs_dir = model_cache / "blobs"
        if blobs_dir.exists() and any(blobs_dir.glob("*.incomplete")):
            return None
        snapshots_dir = model_cache / "snapshots"
        if not snapshots_dir.exists():
            return None
        for snapshot in snapshots_dir.iterdir():
            if not snapshot.is_dir():
                continue
            if _REQUIRED_SNAPSHOT_FILES.issubset({p.name for p in snapshot.iterdir()}):
                return snapshot
        return None

    def _ensure_model(self) -> object:
        """Lazily load and warm up the MLX model."""
        if self._model is not None:
            return self._model  # type: ignore[return-value]
        if self._import_error is not None:
            raise BackendUnavailableError(
                "MLX backend is not installed. Install optional dependency with `.[mlx]`."
            )
        try:
            from qwen3_asr_mlx import Qwen3ASR

            model_source = self._cached_snapshot_path()
            if model_source is not None:
                print(f"asr: loading cached model snapshot {model_source}", file=sys.stderr, flush=True)
            else:
                print(f"asr: resolving model {self._model_id} from Hugging Face Hub", file=sys.stderr, flush=True)
            self._model = Qwen3ASR.from_pretrained(str(model_source) if model_source else self._model_id)
            if not MLXBackend._warmmed_up:
                print("asr: warming up model (first process may take about 1-2 minutes)", file=sys.stderr, flush=True)
                self._model.warm_up()
                print("asr: model warm-up complete", file=sys.stderr, flush=True)
                MLXBackend._warmmed_up = True
            return self._model  # type: ignore[return-value]
        except Exception as exc:
            raise ASRProcessingError(f"Failed to load MLX model: {exc}") from exc

    def _load_audio(self, input_path: Path) -> str:
        """Return path to a 16 kHz mono WAV file, converting if needed via pydub."""
        suffix = input_path.suffix.lower()
        if suffix == ".wav":
            try:
                import wave

                with wave.open(str(input_path), "rb") as wav_file:
                    if wav_file.getframerate() == 16000 and wav_file.getnchannels() == 1:
                        return str(input_path)
            except Exception:
                pass
        try:
            import pydub
        except ImportError as exc:
            raise ASRProcessingError(
                "pydub is required to normalize ASR audio inputs. Install with `pip install pydub`."
            ) from exc
        audio = pydub.AudioSegment.from_file(str(input_path))
        audio = audio.set_frame_rate(16000).set_channels(1)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        audio.export(str(tmp_path), format="wav")
        return str(tmp_path)

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        if not self.available():
            raise BackendUnavailableError(
                "MLX backend is not installed. Install optional dependency with `.[mlx]`."
            )
        model = self._ensure_model()
        tmp_wav_path: Path | None = None
        try:
            audio_path = self._load_audio(request.input_path)
            if audio_path != str(request.input_path):
                tmp_wav_path = Path(audio_path)
            model_kwargs: dict = {}
            if request.prompt is not None:
                model_kwargs["context"] = request.prompt
            if request.language is not None:
                model_kwargs["language"] = request.language
            result = model.transcribe(audio_path, **model_kwargs)
            return TranscriptionResult(
                text=result.text or "",
                output_format=request.output_format,
                backend_name=self.name,
                segments=[],  # qwen3-asr-mlx does not expose word-level segments
                metadata={
                    "language": getattr(result, "language", None),
                    "duration": getattr(result, "duration", None),
                },
            )
        except BackendUnavailableError:
            raise
        except Exception as exc:
            raise ASRProcessingError(f"MLX transcription failed: {exc}") from exc
        finally:
            if tmp_wav_path is not None:
                tmp_wav_path.unlink(missing_ok=True)
