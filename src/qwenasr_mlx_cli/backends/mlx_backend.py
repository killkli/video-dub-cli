from __future__ import annotations

import tempfile
from pathlib import Path

from qwenasr_mlx_cli.core.exceptions import (
    ASRProcessingError,
    BackendUnavailableError,
)
from qwenasr_mlx_cli.core.types import TranscriptionRequest, TranscriptionResult


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

    def _ensure_model(self) -> "Qwen3ASR":
        """Lazily load and warm up the MLX model."""
        if self._model is not None:
            return self._model  # type: ignore[return-value]
        if self._import_error is not None:
            raise BackendUnavailableError(
                "MLX backend is not installed. Install optional dependency with `.[mlx]`."
            )
        try:
            from qwen3_asr_mlx import Qwen3ASR

            self._model = Qwen3ASR.from_pretrained(self._model_id)
            if not MLXBackend._warmmed_up:
                self._model.warm_up()
                MLXBackend._warmmed_up = True
            return self._model  # type: ignore[return-value]
        except Exception as exc:
            raise ASRProcessingError(f"Failed to load MLX model: {exc}") from exc

    def _load_audio(self, input_path: Path) -> str:
        """Return path to a 16 kHz mono WAV file, converting if needed via pydub."""
        suffix = input_path.suffix.lower()
        if suffix == ".wav":
            return str(input_path)
        # Convert non-WAV to a temp WAV using pydub (ffmpeg backend)
        try:
            import pydub
        except ImportError as exc:
            raise ASRProcessingError(
                "pydub is required for non-WAV files. Install with `pip install pydub`."
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
