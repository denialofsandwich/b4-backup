"""Generate a yaml based on the default config defined in `config_schema.py`."""

import pathlib

import yaml
from omegaconf import OmegaConf

from b4_backup.config_schema import (
    BaseConfig,
    OnDestinationDirNotFound,
    SubvolumeBackupStrategy,
    SubvolumeFallbackStrategy,
    TargetRestoreStrategy,
)


def _path_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))


def _enum_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data.name))


yaml.add_representer(pathlib.PosixPath, _path_representer)
yaml.add_representer(TargetRestoreStrategy, _enum_representer)
yaml.add_representer(SubvolumeFallbackStrategy, _enum_representer)
yaml.add_representer(SubvolumeBackupStrategy, _enum_representer)
yaml.add_representer(OnDestinationDirNotFound, _enum_representer)

base_conf = OmegaConf.merge(
    OmegaConf.structured(BaseConfig),
    OmegaConf.load(pathlib.Path(__file__).parent / "config_example.yml"),
)

config: dict = OmegaConf.to_container(base_conf, resolve=True)  # type: ignore

path = pathlib.Path("docs/reference/config.yml")
path.parent.mkdir(parents=True, exist_ok=True)

with path.open("w", encoding="utf8") as file:
    yaml.dump(config, file)
