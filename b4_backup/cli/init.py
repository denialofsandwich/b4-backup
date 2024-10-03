"""Contains the base part of the CLI."""

import logging.config
from pathlib import Path

import omegaconf
import rich
import typer

from b4_backup import utils

app = typer.Typer(pretty_exceptions_enable=False)


def _version_callback(value: bool):
    if value:
        import importlib.metadata

        typer.echo(importlib.metadata.version("b4_backup"))
        raise typer.Exit()


@app.callback()
def init(
    ctx: typer.Context,
    config_path: Path = typer.Option(
        utils.DEFAULT_CONFIG,
        "--config",
        "-c",
        help="Path to the config file",
    ),
    options: list[str] = typer.Option([], "--option", "-o", help="Override values from the config"),
    _version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Print the current version and exit",
    ),
):
    """Backup and restore btrfs subvolumes using btrfs-progs."""
    try:
        config = utils.load_config(config_path, options)
    except omegaconf.errors.OmegaConfBaseException as exc:
        rich.print(f"[red]You got an error in your configuration file {config_path}:")
        rich.print(exc)
        raise typer.Exit(1) from exc

    logging.config.dictConfig(config.logging)

    ctx.obj = config
