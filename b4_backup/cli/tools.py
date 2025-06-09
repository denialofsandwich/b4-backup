"""Helpful cli commands, that are too specific to be in the main part of the code.

Some parts here may be untested.
"""

import io
import json
import logging

import rich
import typer
from omegaconf import OmegaConf
from rich.syntax import Syntax

from b4_backup import config_schema
from b4_backup.cli import utils
from b4_backup.main import backup_target_host, dataclass

log = logging.getLogger("b4_backup.cli")

app = typer.Typer(help=__doc__)


@app.command()
def dump_config(ctx: typer.Context):
    """Return the fully interpolated configuration. For debugging."""
    config: config_schema.BaseConfig = ctx.obj

    rich.print(Syntax(OmegaConf.to_yaml(config), "yaml", line_numbers=True))


@app.command()
def update_config(  # pragma: no cover
    ctx: typer.Context,
    new_targets: str = typer.Argument(..., help="JSON object containing 'target_name: source'"),
    dry_run: bool = typer.Option(
        False, help="Just print the new config instead of actually updating the config file"
    ),
):
    """Updates the b4 config based on the new targets list parameter.

    Targets that are not mentioned in the new targets list, aren't removed,
    but the source attribute will become None, until every backup is eventually deleted or cleaned.

    You need to provide the config updates in a format like this:
    {"localhost/test": "/new_source", "example.com/test": "ssh://root@example.com/test"}

    ruaml.yaml required.
    """
    from ruamel.yaml import YAML

    yaml = YAML()

    config: config_schema.BaseConfig = ctx.obj

    with utils.error_handler():
        config_yaml = yaml.load(config.config_path)
        new_target_objs = json.loads(new_targets)

        target_choice = dataclass.ChoiceSelector(list(config.backup_targets))
        passive_targets = {
            dst_host.name: len(dst_host.snapshots())
            for _none, dst_host in backup_target_host.host_generator(
                target_choice, config.backup_targets, use_source=False
            )
            if dst_host
        }

        for target_name, source in new_target_objs.items():
            if target_name in passive_targets:
                config_yaml["backup_targets"][target_name]["source"] = source
            else:
                config_yaml["backup_targets"][target_name] = {"source": source}

        for target_name in set(passive_targets.keys() - new_target_objs.keys()):
            if passive_targets[target_name] > 0:
                config_yaml["backup_targets"][target_name]["source"] = None
            else:
                del config_yaml["backup_targets"][target_name]

        config_yaml["default_targets"] = list(new_target_objs)

        strio = io.StringIO()
        yaml.dump(config_yaml, strio)
        strio.seek(0)
        new_config_yaml = strio.read()

        if dry_run:
            rich.print(Syntax(new_config_yaml, "yaml", line_numbers=True))
        else:
            config.config_path.write_text(new_config_yaml)
