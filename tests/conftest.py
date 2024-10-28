"""Pytest fixture collection."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from b4_backup import utils
from b4_backup.config_schema import BaseConfig
from b4_backup.main.backup_target_host import BackupTargetHost
from b4_backup.main.connection import LocalConnection


@pytest.fixture(scope="session")
def config_path() -> Generator[Path, None, None]:
    """Returns a path to the test config file."""
    original_path = Path(__file__).parent / "config.yml"

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_conf = Path(tmp_dir) / "config.yml"
        shutil.copyfile(original_path, test_conf)

        yield test_conf


@pytest.fixture(scope="session")
def config(config_path: Path) -> BaseConfig:
    """Returns a temporary config object based on config_path."""
    return utils.load_config(config_path, [])


@pytest.fixture(scope="class")
def volume(config_path: Path) -> Generator[Path, None, None]:
    """Create a temporary btrfs volume and return the mount point path."""
    volume_file = config_path.parent / "btrfs_file"
    mount_point = Path("/opt")

    os.system(f"/code/tests/create_btrfs_volume.sh mount {volume_file} {mount_point}")

    os.system(f"btrfs subvolume create {mount_point / 'test'}")
    (mount_point / "test/file.txt").write_text("hello world")

    yield mount_point

    os.system(f"/code/tests/create_btrfs_volume.sh umount {volume_file} {mount_point}")


@pytest.fixture
def src_host(config: BaseConfig, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(BackupTargetHost, "_mount_point", MagicMock(return_value=Path("/opt")))

    target_name = "localhost/home"
    return BackupTargetHost.from_source_host(
        target_name=target_name,
        target_config=config.backup_targets[target_name],
        connection=LocalConnection(Path("/home")),
    )


@pytest.fixture
def dst_host(config: BaseConfig):
    target_name = "localhost/home"
    return BackupTargetHost.from_destination_host(
        target_name=target_name,
        target_config=config.backup_targets[target_name],
        connection=LocalConnection(Path("/opt/b4")),
    )
