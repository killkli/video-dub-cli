from pydantic import BaseModel


class PathsConfig(BaseModel):
    cache_dir: str = "~/Library/Caches/qwenasr-mlx"
    models_dir: str = "~/Library/Application Support/qwenasr-mlx/models"


class AppConfig(BaseModel):
    backend: str = "mlx"
    model: str = "mlx-community/Qwen3-ASR-1.7B-bf16"
    output_format: str = "txt"
    paths: PathsConfig = PathsConfig()
