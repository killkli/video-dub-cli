from typing import Protocol

from qwenasr_mlx_cli.core.types import TranscriptionRequest, TranscriptionResult


class ASRBackend(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        ...
