"""
This scripts generates a markdown cli reference.

Code base from:
    https://github.com/tiangolo/typer-cli
    Copyright (c) 2020 Sebastián Ramírez

"""

from pathlib import Path
from typing import cast

import typer
import typer.core
from click import Command, Group

from b4_backup.cli import app as target_app


def _get_docs_for_click(  # noqa: C901,PLR0915,PLR0912
    *,
    obj: Command,
    ctx: typer.Context,
    indent: int = 0,
    name: str = "",
    call_prefix: str = "",
) -> str:
    docs = "#" * (1 + indent)
    command_name = name or obj.name
    if call_prefix:
        command_name = f"{call_prefix} {command_name}"
    title = f"`{command_name}`" if command_name else "CLI"
    docs += f" {title}\n\n"
    if obj.help:
        docs += f"{obj.help}\n\n"
    usage_pieces = obj.collect_usage_pieces(ctx)
    if usage_pieces:
        docs += "**Usage**:\n\n"
        docs += "```console\n"
        docs += "$ "
        if command_name:
            docs += f"{command_name} "
        docs += f"{' '.join(usage_pieces)}\n"
        docs += "```\n\n"
    args = []
    opts = []
    for param in obj.get_params(ctx):
        rv = param.get_help_record(ctx)
        if rv is not None:
            if param.param_type_name == "argument":
                args.append(rv)
            elif param.param_type_name == "option":
                opts.append(rv)
    if args:
        docs += "**Arguments**:\n\n"
        for arg_name, arg_help in args:
            docs += f"* `{arg_name}`"
            if arg_help:
                docs += f": {arg_help}"
            docs += "\n"
        docs += "\n"
    if opts:
        docs += "**Options**:\n\n"
        for opt_name, opt_help in opts:
            docs += f"* `{opt_name}`"
            if opt_help:
                docs += f": {opt_help}"
            docs += "\n"
        docs += "\n"
    if obj.epilog:
        docs += f"{obj.epilog}\n\n"
    if isinstance(obj, Group):
        group: Group = cast(Group, obj)
        commands = group.list_commands(ctx)
        if commands:
            docs += "**Commands**:\n\n"
            for command in commands:
                command_obj = group.get_command(ctx, command)
                assert command_obj
                docs += f"* `{command_obj.name}`"
                command_help = command_obj.get_short_help_str()
                if command_help:
                    docs += f": {command_help}"
                docs += "\n"
            docs += "\n"
        for command in commands:
            command_obj = group.get_command(ctx, command)
            assert command_obj
            use_prefix = ""
            if command_name:
                use_prefix += f"{command_name}"
            docs += _get_docs_for_click(
                obj=command_obj, ctx=ctx, indent=indent + 1, call_prefix=use_prefix
            )
    return docs


def main(
    ctx: typer.Context,
    name: str = typer.Option("", help="The name of the CLI program to use in docs."),
    output: Path = typer.Option(
        None,
        help="An output file to write docs to, like README.md.",
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """Generate Markdown docs for a Typer app."""
    typer_obj = target_app
    if not typer_obj:
        typer.echo("No Typer app found", err=True)
        raise typer.Abort()
    click_obj = typer.main.get_command(typer_obj)
    docs = _get_docs_for_click(obj=click_obj, ctx=ctx, name=name)
    clean_docs = f"{docs.strip()}\n"
    if output:
        output.write_text(clean_docs)
        typer.echo(f"Docs saved to: {output}")
    else:
        typer.echo(clean_docs)


typer.run(main)
