"""Contains code for the main part of the CLI."""

import logging

import typer
from rich import prompt

from b4_backup import exceptions
from b4_backup.cli.init import app
from b4_backup.cli.tools import app as tools_app
from b4_backup.cli.utils import (
    OutputFormat,
    complete_target,
    error_handler,
    validate_target,
)
from b4_backup.config_schema import BaseConfig, TargetRestoreStrategy
from b4_backup.main.b4_backup import B4Backup
from b4_backup.main.backup_target_host import host_generator
from b4_backup.main.dataclass import ChoiceSelector

log = logging.getLogger("b4_backup.cli")

app.add_typer(tools_app, name="tools")


@app.command()
def backup(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    name: str = typer.Option(
        "manual",
        "-n",
        "--name",
        help="Name suffix (and retention ruleset) for this backup",
    ),
    source_only: bool = typer.Option(
        False,
        help="Perform actions on source side only",
    ),
):
    """Perform backups on specified targets. If no target is specified, the default targets defined in the config will be used."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)

    b4_backup = B4Backup(config.timezone)

    with error_handler() as err_handler:
        snapshot_name = b4_backup.generate_snapshot_name(name)

        for src_host, dst_host in host_generator(
            target_choice, config.backup_targets, use_destination=not source_only
        ):
            try:
                if not src_host:
                    raise exceptions.InvalidConnectionUrlError(  # noqa: TRY301
                        "Backup requires source to be specified"
                    )

                b4_backup.backup(src_host, dst_host, snapshot_name)
            except Exception as exc:
                err_handler.add(exc)


@app.command(name="list")
def list_snapshots(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    source: bool = typer.Option(False, help="List snapshots on source host"),
    destination: bool = typer.Option(False, help="List snapshots on destination host"),
    format: OutputFormat = typer.Option(OutputFormat.RICH.value, help="Output format"),
):
    """List all snapshots for the specified targets."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)
    with error_handler():
        for src_host, dst_host in host_generator(
            target_choice,
            config.backup_targets,
            use_source=source,
            use_destination=destination,
        ):
            if src_host:
                OutputFormat.output(src_host.snapshots(), "Source", format)
            if dst_host:
                OutputFormat.output(dst_host.snapshots(), "Destination", format)


@app.command()
def clean(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    source_only: bool = typer.Option(
        False,
        help="Perform actions on source side only",
    ),
):
    """Apply the targets retention ruleset without performing a backup."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)

    b4_backup = B4Backup(config.timezone)

    with error_handler():
        for src_host, dst_host in host_generator(
            target_choice, config.backup_targets, use_destination=not source_only
        ):
            if not src_host:
                raise exceptions.InvalidConnectionUrlError("Clean requires source to be specified")

            b4_backup.clean(src_host, dst_host)


@app.command()
def delete(
    ctx: typer.Context,
    snapshot_name: str = typer.Argument(..., help="Name of the snapshot you want to restore"),
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    source: bool = typer.Option(False, help="Delete from source host"),
    destination: bool = typer.Option(False, help="Delete from destination host"),
):
    """Delete a specific snapshot from the source and/or destination."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)
    b4_backup = B4Backup(config.timezone)
    with error_handler():
        for src_host, dst_host in host_generator(
            target_choice, config.backup_targets, use_source=source, use_destination=destination
        ):
            if src_host:
                b4_backup.delete(src_host, snapshot_name)
            if dst_host:
                b4_backup.delete(dst_host, snapshot_name)


@app.command()
def delete_all(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    retention: list[str] = typer.Option(
        ["ALL"],
        "-r",
        "--retention",
        help="Name suffix (and retention ruleset) for this backup",
    ),
    force: bool = typer.Option(False, help="Skip confirmation prompt"),
    source: bool = typer.Option(False, help="Delete from source host"),
    destination: bool = typer.Option(False, help="Delete from destination host"),
):
    """Delete all local and remote backups of the specified target/retention ruleset combination. Equivalent to an "all: 0" rule."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)
    retention_names = ChoiceSelector(retention)

    log.warning(
        "You are about to DELETE all snapshots with these retention_names (%s) for these targets: %s",
        ", ".join(retention),
        ", ".join(target_choice.resolve_target(config.backup_targets)),
    )
    if not force and not prompt.Confirm.ask("Continue"):
        raise typer.Exit(1)

    b4_backup = B4Backup(config.timezone)

    with error_handler():
        for src_host, dst_host in host_generator(
            target_choice, config.backup_targets, use_source=source, use_destination=destination
        ):
            if src_host:
                b4_backup.delete_all(src_host, retention_names)

            if dst_host:
                b4_backup.delete_all(dst_host, retention_names)


@app.command()
def restore(
    ctx: typer.Context,
    snapshot_name: str = typer.Argument(..., help="Name of the snapshot you want to restore"),
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
    strategy: TargetRestoreStrategy | None = typer.Option(
        None,
        help="Restore strategy or procedure to apply",
    ),
    source_only: bool = typer.Option(
        False,
        help="Perform actions on source side only",
    ),
):
    """
    Restore one or more targets based on a previously created snapshot.
    You can revert a REPLACE restore by using REPLACE als snapshot name and strategy.
    """
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)

    b4_backup = B4Backup(config.timezone)

    with error_handler():
        for src_host, dst_host in host_generator(
            target_choice, config.backup_targets, use_destination=not source_only
        ):
            if not src_host:
                raise exceptions.InvalidConnectionUrlError(
                    "Restore requires source to be specified"
                )

            target_strategy = strategy or src_host.target_config.restore_strategy

            b4_backup.restore(src_host, dst_host, snapshot_name, target_strategy)


@app.command()
def sync(
    ctx: typer.Context,
    target: list[str] = typer.Option(
        [],
        "-t",
        "--target",
        help="Selected targets to backup",
        autocompletion=complete_target,
        callback=validate_target,
    ),
):
    """Send pending snapshots to the destination."""
    config: BaseConfig = ctx.obj
    target_choice = ChoiceSelector(target or config.default_targets)

    b4_backup = B4Backup(config.timezone)

    with error_handler():
        for src_host, dst_host in host_generator(target_choice, config.backup_targets):
            if not src_host or not dst_host:
                raise exceptions.InvalidConnectionUrlError(
                    "Sync requires source and destination to be specified"
                )

            b4_backup.sync(src_host, dst_host)


# A collection of stuff I would like to improve

## Tooling
# TODO: Replace poetry with uv

## Features
# TODO: pre/post backup hooks
#   - Option to execute code before and after an update
#     Would be handy for enabling maintanance mode during an update

## Documentation
# TODO: Docs
# - Auto create links to reference and terminology

## Visual CLI and logging improvements
# TODO: b4 cmd without any options should show --help text
# TODO: rich print_log function
#   - To optionally print logs like a standard rich.print()
#   - Will be in a seperate logger. Maybe b4_backup.print
#   - Subvolume transmission info (Bytes transfered, duration, rate)

# TODO: List snapshots flags
#   - Show status of snapshot for example: stale, async

# TODO: b4 switch command to switch to version:
#   - b4 switch source to go to the source directory if available
#   - Needs to be executed using "cd $(b4 switch 2024-05-21-14-41-10_manual)"
#   - A better approach would be a modification in bashrc/zshrc
#   - Implement autocomplete for snapshots
