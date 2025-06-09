import shlex
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from b4_backup import utils
from b4_backup.cli import main
from b4_backup.cli.init import app
from b4_backup.cli.utils import OutputFormat
from b4_backup.config_schema import BaseConfig
from b4_backup.main.b4_backup import B4Backup

runner = CliRunner()


@pytest.mark.parametrize(
    ("cmd", "extra_args"),
    [
        ("backup", ""),
        ("clean", ""),
        ("restore", "alpha_manual"),
        ("sync", ""),
        ("delete", "--no-source --destination alpha_manual"),
        ("delete", "--source --no-destination alpha_manual"),
        ("delete_all", "--force --no-source --destination"),
        ("delete_all", "--force --source --no-destination"),
    ],
)
def test_basic_cmd(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    cmd: str,
    extra_args: str,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(
        main,
        "host_generator",
        MagicMock(
            return_value=[
                (
                    None if "no-source" in extra_args else MagicMock(),
                    None if "no-destination" in extra_args else MagicMock(),
                ),
            ]
        ),
    )
    fake_cmd = MagicMock()
    monkeypatch.setattr(B4Backup, cmd, fake_cmd)

    # Act
    result = runner.invoke(
        app,
        shlex.split(
            f"-c tests/config.yml {cmd.replace('_', '-')} --target localhost/home {extra_args}"
        ),
    )

    # Assert
    print(result.exc_info)
    print(result.stdout)

    assert fake_cmd.call_count == 1
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("cmd", "extra_args"),
    [
        ("backup", ""),
        ("clean", ""),
        ("restore", "alpha_manual"),
    ],
)
def test_basic_cmd__host_required(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    cmd: str,
    extra_args: str,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(
        main,
        "host_generator",
        MagicMock(
            return_value=[
                (None, MagicMock()),
            ]
        ),
    )

    # Act
    result = runner.invoke(
        app, shlex.split(f"-c tests/config.yml {cmd} --target localhost/home {extra_args}")
    )

    # Assert
    assert result.exit_code == 1
    assert "requires source" in result.stdout


def test_backup__error_group(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(
        main,
        "host_generator",
        MagicMock(
            return_value=[
                (MagicMock(), None),
            ]
        ),
    )
    monkeypatch.setattr(
        B4Backup,
        "backup",
        MagicMock(side_effect=[ExceptionGroup("GroupERROR", [Exception()])]),
    )

    # Act
    result = runner.invoke(app, shlex.split("-c tests/config.yml backup --target localhost/home"))

    # Assert
    assert result.exit_code == 1
    assert "GroupERROR" in result.stdout


@pytest.mark.parametrize(
    "extra_args",
    [
        "--no-source --destination",
        "--source --no-destination",
    ],
)
def test_list_snapshots(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    extra_args: str,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(
        main,
        "host_generator",
        MagicMock(
            return_value=[
                (
                    None if "no-source" in extra_args else MagicMock(),
                    None if "no-destination" in extra_args else MagicMock(),
                ),
            ]
        ),
    )
    fake_output = MagicMock()
    monkeypatch.setattr(OutputFormat, "output", fake_output)

    # Act
    result = runner.invoke(
        app,
        shlex.split(f"-c tests/config.yml list --target localhost/home {extra_args}"),
    )

    # Assert
    print(result.exc_info)
    print(result.stdout)

    assert fake_output.call_count == 1
    assert result.exit_code == 0


def test_delete_all__abort(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(main.prompt.Confirm, "ask", MagicMock(return_value=False))

    # Act
    result = runner.invoke(app, shlex.split("-c tests/config.yml delete-all"))

    # Assert
    assert result.exit_code == 1


def test_sync__error(
    config: BaseConfig,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))
    monkeypatch.setattr(
        main,
        "host_generator",
        MagicMock(
            return_value=[
                (MagicMock(), None),
            ]
        ),
    )

    # Act
    result = runner.invoke(app, shlex.split("-c tests/config.yml sync --target localhost/home"))

    # Assert
    assert result.exit_code == 1
    assert "Sync requires source and destination" in result.stdout
