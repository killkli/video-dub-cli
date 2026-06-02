import click


@click.group()
@click.version_option()
def main():
    """video-dub-cli — single command to dub any video."""
    pass


@main.command()
@click.argument("video", type=click.Path(exists=True))
@click.option("--source-lang", default=None)
@click.option("--target-lang", default=None)
@click.option("--project-dir", type=click.Path(), default=None)
@click.option("--config", "config_path", type=click.Path(), default=None)
@click.option(
    "--translate-mode",
    type=click.Choice(["delegate", "skip", "use-existing"]),
    default="delegate",
)
@click.option("--translated-srt", type=click.Path(), default=None)
@click.option("--vocal-gain", type=float, default=None)
@click.option("--inst-gain", type=float, default=None)
@click.option("--keep-fulltrack", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
def run(video, source_lang, target_lang, project_dir, config_path,
        translate_mode, translated_srt, vocal_gain, inst_gain,
        keep_fulltrack, yes):
    """Run full dubbing pipeline. VIDEO is the source mp4 path."""
    click.echo(f"run: VIDEO={video} src={source_lang} tgt={target_lang}")


@main.command(name="resume")
@click.option("--project-dir", required=True, type=click.Path(exists=True))
def resume_cmd(project_dir):
    """Resume an interrupted pipeline from last successful stage."""
    click.echo(f"resume: project={project_dir}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True))
def status(project_dir):
    """Show stage-by-stage pipeline status."""
    click.echo(f"status: project={project_dir}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True))
@click.option("--keep-source", is_flag=True, default=True)
@click.option("--stage", type=int, default=None)
def clean(project_dir, keep_source, stage):
    """Clean partial pipeline artifacts."""
    click.echo(f"clean: project={project_dir} stage={stage}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True))
def validate(project_dir):
    """Validate project structure and outputs."""
    click.echo(f"validate: project={project_dir}")