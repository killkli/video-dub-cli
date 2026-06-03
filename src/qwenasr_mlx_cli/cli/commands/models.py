from rich.console import Console

from qwenasr_mlx_cli.config.loader import load_config


def models_list_command() -> None:
    console = Console()
    config = load_config()
    console.print(f"default: {config.model}")
    console.print("planned aliases:")
    console.print("- mlx-community/Qwen3-ASR-1.7B-bf16")
    console.print("- mlx-community/Qwen3-ASR-0.6B-bf16")
