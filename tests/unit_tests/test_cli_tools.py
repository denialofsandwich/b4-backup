import shlex
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from b4_backup import utils
from b4_backup.cli.init import app
from b4_backup.config_schema import BaseConfig

runner = CliRunner()


def test_dump_config(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))

    # Act
    result = runner.invoke(app, shlex.split("-c tests/config.yml tools dump-config"))

    # Assert
    assert result.exit_code == 0
