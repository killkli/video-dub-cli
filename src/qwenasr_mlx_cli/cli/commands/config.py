from rich.console import Console

from qwenasr_mlx_cli.config.loader import load_config
from qwenasr_mlx_cli.config.paths import default_config_path


def config_show_command() -> None:
    console = Console()
    console.print(load_config().model_dump_json(indent=2))


def config_path_command() -> None:
    console = Console()
    console.print(str(default_config_path()))
