import typer

from qwenasr_mlx_cli.cli.commands.batch import batch_command
from qwenasr_mlx_cli.cli.commands.config import config_path_command, config_show_command
from qwenasr_mlx_cli.cli.commands.doctor import doctor_command
from qwenasr_mlx_cli.cli.commands.models import models_list_command
from qwenasr_mlx_cli.cli.commands.prefetch import prefetch_command
from qwenasr_mlx_cli.cli.commands.transcribe import transcribe_command

app = typer.Typer(help="QwenASR MLX CLI")
config_app = typer.Typer(help="Configuration commands")
models_app = typer.Typer(help="Model commands")

app.command("doctor")(doctor_command)
app.command("transcribe")(transcribe_command)
app.command("batch")(batch_command)
app.command("prefetch")(prefetch_command)
config_app.command("show")(config_show_command)
config_app.command("path")(config_path_command)
models_app.command("list")(models_list_command)
app.add_typer(config_app, name="config")
app.add_typer(models_app, name="models")


def main() -> None:
    app()
