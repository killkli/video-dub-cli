from dataclasses import replace
from typing import Protocol

from qwenasr_mlx_cli.core.exceptions import ASRProcessingError
from qwenasr_mlx_cli.core.types import TranscriptionResult


class _Converter(Protocol):
    def convert(self, text: str) -> str: ...


def _build_converter() -> _Converter:
    try:
        from opencc import OpenCC
    except Exception as exc:  # pragma: no cover
        raise ASRProcessingError(
            "OpenCC is required for simplified-to-traditional conversion. "
            "Install with `pip install opencc`."
        ) from exc
    return OpenCC("s2twp")


def convert_simplified_to_traditional_text(text: str) -> str:
    converter = _build_converter()
    return converter.convert(text)


def convert_result_to_traditional(result: TranscriptionResult) -> TranscriptionResult:
    converter = _build_converter()
    converted_segments = [
        replace(segment, text=converter.convert(segment.text)) for segment in result.segments
    ]
    return replace(
        result,
        text=converter.convert(result.text),
        segments=converted_segments,
    )
