from __future__ import annotations

import shutil
from pathlib import Path

import click

from dub.config import load_config
from dub.project import STAGE_DIRS, create_project, initialize_project, project_input_info
from dub.runner import run_pipeline
from dub.state import load_state, new_state, save_state


def _prepare_project(video: Path, project_dir: str | None, cfg) -> Path:
    if project_dir:
        pdir = Path(project_dir)
        if pdir.exists() and (pdir / ".dub" / "state.json").exists():
            return pdir
        return initialize_project(pdir, video)
    return create_project(cfg.paths.dub_root, video)


def _bootstrap_state(project_dir: Path, cfg) -> None:
    state_path = project_dir / ".dub" / "state.json"
    if state_path.exists():
        return
    state = new_state(project_dir, cfg)
    info = project_input_info(project_dir)
    state.input["video_path"] = info["video_path"]
    state.input["video_sha256"] = info["video_sha256"]
    state.input["duration_sec"] = info["duration_sec"]
    state.input["translate_mode"] = cfg.translation.mode
    state.input["translated_srt"] = str(cfg.translation.translated_srt) if cfg.translation.translated_srt else None
    save_state(project_dir, state)


def _refresh_runtime_input_state(project_dir: Path, cfg) -> None:
    state = load_state(project_dir)
    state.input["source_lang"] = cfg.defaults.source_lang
    state.input["target_lang"] = cfg.defaults.target_lang
    state.input["translate_mode"] = cfg.translation.mode
    state.input["translated_srt"] = str(cfg.translation.translated_srt) if cfg.translation.translated_srt else None
    save_state(project_dir, state)


@click.group()
@click.version_option()
def main():
    """video-dub-cli — single command to dub any video."""
    pass


@main.command()
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option("--source-lang", "source_lang", default=None)
@click.option("--target-lang", "target_lang", default=None)
@click.option("--project-dir", type=click.Path(path_type=Path), default=None)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--translate-mode",
    type=click.Choice(["delegate", "skip", "use-existing"]),
    default="delegate",
)
@click.option("--translated-srt", type=click.Path(path_type=Path), default=None)
@click.option("--vocal-gain", type=float, default=None)
@click.option("--inst-gain", type=float, default=None)
@click.option("--keep-fulltrack", is_flag=True, default=False)
@click.option("--yes", "-y", is_flag=True, default=False)
def run(video, source_lang, target_lang, project_dir, config_path,
        translate_mode, translated_srt, vocal_gain, inst_gain,
        keep_fulltrack, yes):
    """Run full dubbing pipeline. VIDEO is the source mp4 path."""
    cfg = load_config(config_path)
    cfg = cfg.merge_cli_overrides(
        source_lang=source_lang,
        target_lang=target_lang,
        vocal_gain=vocal_gain,
        inst_gain=inst_gain,
        keep_fulltrack=keep_fulltrack,
        translate_mode=translate_mode,
        translated_srt=translated_srt,
    )
    pdir = _prepare_project(video, str(project_dir) if project_dir else None, cfg)
    _bootstrap_state(pdir, cfg)
    _refresh_runtime_input_state(pdir, cfg)
    run_pipeline(pdir, cfg, yes=yes)
    click.echo(f"run complete: project={pdir}")


@main.command(name="resume")
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def resume_cmd(project_dir, config_path):
    """Resume an interrupted pipeline from last successful stage."""
    cfg = load_config(config_path)
    project_dir.mkdir(parents=True, exist_ok=True)
    if not (project_dir / "01_raw_video" / "video.mp4").exists():
        click.echo(f"resume: project={project_dir} (no source video)")
        return
    _bootstrap_state(project_dir, cfg)
    run_pipeline(project_dir, cfg, yes=True)
    click.echo(f"resume complete: project={project_dir}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
def status(project_dir):
    """Show stage-by-stage pipeline status."""
    try:
        state = load_state(project_dir)
    except FileNotFoundError:
        click.echo(f"status: project={project_dir} (no state)")
        return
    for name, st in state.stages.items():
        click.echo(f"{name}: {st.status} attempts={st.attempts}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--keep-source/--remove-source", default=True)
@click.option("--stage", type=int, default=None)
def clean(project_dir, keep_source, stage):
    """Clean partial pipeline artifacts."""
    if stage is None:
        targets = [d for d in STAGE_DIRS if keep_source or d != "01_raw_video"] + [".dub"]
    else:
        stage_map = {
            1: ["02_stems"],
            2: ["03_asr"],
            3: ["04_ref_audio"],
            4: ["05_translate", "05_translated_srt"],
            5: ["06_tts_wav"],
            6: ["07_final"],
        }
        targets = stage_map.get(stage, [])
    for rel in targets:
        target = project_dir / rel
        if target.exists():
            shutil.rmtree(target)
        if rel != ".dub":
            target.mkdir(parents=True, exist_ok=True)
    click.echo(f"clean complete: project={project_dir} stage={stage}")


@main.command()
@click.option("--project-dir", required=True, type=click.Path(exists=True, path_type=Path))
def validate(project_dir):
    """Validate project structure and outputs."""
    missing = []
    for rel in ["01_raw_video", "02_stems", "03_asr", "04_ref_audio", "05_translate", "06_tts_wav", "07_final", ".dub"]:
        if not (project_dir / rel).exists():
            missing.append(rel)
    if missing:
        click.echo(f"validate: project={project_dir} missing={','.join(missing)}")
        return
    try:
        state = load_state(project_dir)
        stage_count = len(state.stages)
    except FileNotFoundError:
        stage_count = 0
    click.echo(f"validate ok: project={project_dir} stages={stage_count}")
