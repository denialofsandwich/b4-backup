from pathlib import Path, PurePath
from unittest.mock import MagicMock

import pytest
import typer
from click import Command

from b4_backup import cli, exceptions, utils
from b4_backup.cli import utils as cli_utils
from b4_backup.config_schema import BaseConfig
from b4_backup.main.dataclass import Snapshot


def test_validate_target__success(config: BaseConfig):
    # Arrange
    mock_ctx = MagicMock()
    mock_ctx.obj = config

    # Act
    result = cli_utils.validate_target(mock_ctx, ["localhost/home"])

    # Assert
    assert result == ["localhost/home"]


def test_parse_callback_args():
    # Act
    parsed_args = cli_utils.parse_callback_args(
        cli.app,
        ["b4", "-c", "ignored", "-c", "b4_backup.yml", "--option", "value1", "-o", "value2"],
    )

    # Assert
    print(parsed_args)
    assert parsed_args == {
        "config_path": Path("b4_backup.yml"),
        "options": ["value1", "value2"],
        "_version": False,
    }


def test_parse_callback_args__default_args():
    # Act
    parsed_args = cli_utils.parse_callback_args(cli.app, ["bb"])

    # Assert
    print(parsed_args)
    assert parsed_args == {
        "config_path": Path("~/.config/b4_backup.yml"),
        "options": [],
        "_version": False,
    }


def test_validate_target__error(config: BaseConfig):
    # Arrange
    mock_ctx = MagicMock()
    mock_ctx.obj = config

    # Act / Assert
    with pytest.raises(typer.BadParameter):
        cli_utils.validate_target(mock_ctx, ["idontexist"])


def test_complete_target(config: BaseConfig, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    ctx = typer.Context(Command("b4"))
    monkeypatch.setenv("_TYPER_COMPLETE_ARGS", "b4 -c tests/config.yml backup --target localh")
    monkeypatch.setattr(utils, "load_config", MagicMock(return_value=config))

    # Act
    result = cli_utils.complete_target(ctx, "localh")

    # Assert
    assert list(result) == [
        "localhost",
        "localhost/home",
        "localhost/mnt",
        "localhost/root",
    ]


class TestErrorHandler:
    def test_empty(self):
        # Arrange
        handler = cli_utils.ErrorHandler()

        # Act
        handler.finalize()

    def test_error(self):
        # Arrange
        handler = cli_utils.ErrorHandler()
        handler.add(Exception())

        # Act
        with pytest.raises(ExceptionGroup):
            handler.finalize()


def test_error_handler__success():
    # Act / Assert
    with cli_utils.error_handler():
        ...


@pytest.mark.parametrize(
    "error",
    [
        exceptions.InvalidConnectionUrlError,
        ValueError,
    ],
)
def test_error_handler__error(error: Exception):
    # Act / Assert
    with (
        pytest.raises(typer.Exit),
        cli_utils.error_handler(),
    ):
        raise error


@pytest.mark.parametrize(
    ("format", "expect"),
    [
        (cli_utils.OutputFormat.RICH, None),
        (
            cli_utils.OutputFormat.JSON,
            '{\n  "host": "source",\n  "snapshots": {\n    "bla_test": []\n  }\n}',
        ),
        (cli_utils.OutputFormat.RAW, ""),
    ],
)
class TestOutputFormat:
    def test_output(
        self,
        format: cli_utils.OutputFormat,
        expect: str | None,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        fake_print = MagicMock()
        monkeypatch.setattr(cli_utils.utils.CONSOLE, "print", fake_print)

        # Act
        cli_utils.OutputFormat.output(
            {
                "bla_test": Snapshot(
                    name="bla_test",
                    subvolumes=[],
                    base_path=PurePath(),  # type: ignore
                )
            },
            title="source",
            output_format=format,
        )  # type: ignore

        # Assert
        if expect is not None:
            fake_print.assert_called_once_with(expect)
        else:
            assert isinstance(fake_print.call_args.args[0], cli_utils.Table)
