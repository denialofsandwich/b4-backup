import tempfile
from pathlib import Path

import pytest
from rich.logging import RichHandler

from b4_backup import utils


def test_rich_handler():
    # Act
    result = utils.rich_handler()

    # Assert
    assert isinstance(result, RichHandler)


def test_resolve_parent_dir():
    # Act
    result = utils.resolve_parent_dir("/etc/test.txt")

    # Assert
    assert result == "/etc"


def test_resolve_from_file(config_path: Path):
    # Arrange
    test_file = config_path.parent / "config_value.txt"
    test_file.write_text(" el_psy_congroo\n")

    # Act
    result = utils.resolve_from_file(str(test_file))

    # Assert
    assert result == "el_psy_congroo"


def test_load_config_minimal():
    with tempfile.TemporaryDirectory() as tdir:
        # Act
        empty_conf = utils.load_config(Path(tdir) / "idontexist", [])

        # Assert
        assert empty_conf.backup_targets["_default"].destination is None
        assert empty_conf.timezone == "utc"


def test_load_config_existing(config_path: Path):
    # Act
    config = utils.load_config(config_path)

    # Assert
    target1 = config.backup_targets["localhost/home"]
    assert "1days" not in target1.dst_retention["auto"]
    assert target1.dst_retention["test"]["all"] == "4"

    target2 = config.backup_targets["localhost/root"]
    assert target2.dst_retention["auto"]["1days"] == "1months"

    assert config.backup_targets.keys() == {
        "_default",
        "localhost/home",
        "localhost/root",
        "localhost/mnt",
    }


@pytest.mark.parametrize(
    ("path", "subpath", "expected_result"),
    [
        (Path("/home/test/.cache/pypoetry/virtualenvs"), Path(".cache/pypoetry"), True),
        (Path("/home/test/.cache/darktable/profile"), Path(".cache/pypoetry"), False),
        (Path("/home/test"), Path("/home/test"), True),
        (Path("/home/test/pictures"), Path("/test/pictures"), False),
    ],
)
def test_contains_path(path: Path, subpath: Path, expected_result: bool):
    # Act
    result = utils.contains_path(path, subpath)

    # Assert
    assert result == expected_result
