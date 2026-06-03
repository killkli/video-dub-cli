from pathlib import Path


def user_config_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "qwenasr-mlx"


def default_config_path() -> Path:
    return user_config_dir() / "config.toml"
