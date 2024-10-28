import json
import logging
import os
import shlex
from contextlib import contextmanager
from enum import Enum
from pathlib import PurePath
from typing import Generator

import rich
import typer
from rich.table import Table

from b4_backup import utils
from b4_backup.cli.init import app, init
from b4_backup.config_schema import DEFAULT, BaseConfig
from b4_backup.exceptions import BaseBtrfsBackupError
from b4_backup.main.dataclass import Snapshot

log = logging.getLogger("b4_backup.cli")


def validate_target(ctx: typer.Context, values: list[str]) -> list[str]:
    """A handler to validate target types."""
    config: BaseConfig = ctx.obj

    options = set(config.backup_targets) - {DEFAULT}
    for value in values:
        if value is not None and not any(PurePath(x).is_relative_to(value) for x in options):
            raise typer.BadParameter(f"Unknown target. Available targets are: {','.join(options)}")

    return values


def complete_target(ctx: typer.Context, incomplete: str) -> Generator[str, None, None]:
    """A handler to provide autocomplete for target types."""
    args = shlex.split(os.getenv("_TYPER_COMPLETE_ARGS", ""))
    parsed_args = utils.parse_callback_args(app, args)
    init(ctx, **parsed_args)
    config: BaseConfig = ctx.obj

    options = set()
    for target in set(config.backup_targets) - {DEFAULT}:
        options.add(target)
        options |= {str(x) for x in PurePath(target).parents}

    options = sorted(options)
    taken_targets = ctx.params.get("target") or []
    for target in options:
        if str(target).startswith(incomplete) and target not in taken_targets:
            yield target


@contextmanager
def error_handler():
    """A wrapper around the CLI error handler."""
    try:
        yield None
    except BaseBtrfsBackupError as exc:
        log.debug("An error occured (%s)", type(exc).__name__, exc_info=exc)
        rich.print(f"[red]An error occured ({type(exc).__name__})")
        rich.print(exc)
        raise typer.Exit(1) from exc
    except Exception as exc:
        log.exception("An unknown error occured (%s)", type(exc).__name__)
        rich.print(f"[red]An unknown error occured ({type(exc).__name__})")
        rich.print(exc)
        raise typer.Exit(1) from exc


class OutputFormat(str, Enum):
    """An enumeration of supported output formats."""

    RICH = "rich"
    JSON = "json"
    RAW = "raw"

    @classmethod
    def output(
        cls,
        snapshots: dict[str, Snapshot],
        title: str,
        output_format: "OutputFormat",
    ) -> None:
        """
        Output the snapshots in the specified format.

        Args:
            snapshots: The snapshots to output
            title: The title of the output
            output_format: The format to output the snapshots in
        """
        if output_format == OutputFormat.RICH:
            cls.output_rich(snapshots, title)
        elif output_format == OutputFormat.JSON:
            cls.output_json(snapshots, title)
        else:
            cls.output_raw(snapshots, title)

    @classmethod
    def output_rich(cls, snapshots: dict[str, Snapshot], title: str) -> None:
        """Output the snapshots in a rich format."""
        table = Table(title=title)

        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Subvolumes", style="magenta")

        for snapshot_name in sorted(snapshots, reverse=True):
            table.add_row(
                snapshot_name,
                "\n".join(
                    [str(PurePath("/") / x) for x in snapshots[snapshot_name].subvolumes_unescaped]
                ),
            )

        utils.CONSOLE.print(table)

    @classmethod
    def output_json(cls, snapshots: dict[str, Snapshot], title: str) -> None:
        """Output the snapshots in a JSON format."""
        utils.CONSOLE.print(
            json.dumps(
                {
                    "host": title.lower(),
                    "snapshots": {
                        snapshot_name: [
                            str(PurePath("/") / x) for x in snapshot.subvolumes_unescaped
                        ]
                        for snapshot_name, snapshot in snapshots.items()
                    },
                },
                sort_keys=True,
                indent=2,
            )
        )

    @classmethod
    def output_raw(cls, snapshots: dict[str, Snapshot], title: str) -> None:
        """Output the snapshots in a raw format."""
        utils.CONSOLE.print(
            "\n".join(
                [
                    f"{title.lower()} {snapshot_name} {str(PurePath(' / ') / subvolume)}"
                    for snapshot_name, snapshot in snapshots.items()
                    for subvolume in snapshot.subvolumes_unescaped
                ]
            )
        )
