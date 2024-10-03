import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from b4_backup import cli

runner = CliRunner()


@pytest.mark.skip
def test_backup_subvolume_ssh(config_path: Path, volume: Path):
    # Act
    result = runner.invoke(
        cli.app,
        shlex.split(f"-c {config_path} backup --target localhost/default/test"),
    )

    # Assert
    print(result.stdout)
    assert result.exit_code == 0

    print((volume / "backup/snapshots/localhost/default/test)").glob("*"))
