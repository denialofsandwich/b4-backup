import importlib.metadata
import shlex
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from b4_backup.cli.init import app

runner = CliRunner()


@app.command()
def command_test():
    print("It works")


def test_config_error():
    # Act
    result = runner.invoke(
        app,
        shlex.split("-c tests/config.yml -o idontexist=1 backup"),
    )

    # Assert
    print(result.exc_info)
    print(result.stdout)

    assert result.exit_code == 1
    assert "error in your configuration file" in result.stdout


def test_version(monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(importlib.metadata, "version", MagicMock(return_value="2.0.1"))

    # Act
    result = runner.invoke(app, shlex.split("--version"))

    # Assert
    print(result.exc_info)
    print(result.stdout)

    assert result.exit_code == 0
    assert result.stdout == "2.0.1\n"


def test_command_test():
    # Act
    result = runner.invoke(app, shlex.split("command-test"))

    # Assert
    print(result.exc_info)
    print(result.stdout)
    assert result.exit_code == 0
    assert result.stdout == "It works\n"
