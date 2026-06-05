"""dub.stages package."""
from dub.stages.base import (
    Stage,
    STAGE_REGISTRY,
    get_stage,
    ASRStage,
    RefAudioStage,
    TTSStage,
    AssembleStage,
)
from dub.stages.stems import StemsStage
from dub.stages.translate import TranslateStage

AsrStage = ASRStage
TtsStage = TTSStage

__all__ = [
    "Stage",
    "STAGE_REGISTRY",
    "get_stage",
    "StemsStage",
    "ASRStage",
    "AsrStage",
    "RefAudioStage",
    "TranslateStage",
    "TTSStage",
    "TtsStage",
    "AssembleStage",
]
