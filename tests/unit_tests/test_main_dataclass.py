from pathlib import PurePath
from unittest.mock import MagicMock

import pytest

from b4_backup import exceptions
from b4_backup.config_schema import BaseConfig
from b4_backup.main.connection import Connection
from b4_backup.main.dataclass import (
    BackupHostPath,
    ChoiceSelector,
    RetentionGroup,
    Snapshot,
)


class TestBackupHostPath:
    def test_basic(self):
        # Arrange
        pure_path = PurePath("a/b/c")
        host_path = BackupHostPath(
            "a/b",
            connection=Connection.from_url("/opt"),
        )

        # Act
        new_path = host_path / "c"

        # Assert
        assert new_path == pure_path

    @pytest.mark.parametrize(
        "data",
        [
            None,
            exceptions.FailedProcessError(["rmdir", "a/b/c"], stderr="No such file or directory"),
        ],
    )
    def test_rmdir(self, data, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock(side_effect=data)
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act
        host_path.rmdir()

        # Assert
        print(fake_run_process.call_args_list)
        fake_run_process.assert_called_once_with(["rmdir", "a/b/c"])

    def test_rmdir__error(self, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock(
            side_effect=exceptions.FailedProcessError(["rmdir", "bla"]),
        )
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act / Assert
        with pytest.raises(exceptions.FailedProcessError):
            host_path.rmdir()

    @pytest.mark.parametrize(
        "data",
        [
            None,
            exceptions.FailedProcessError(
                ["ls", "-d", "a/b/c"], stderr="No such file or directory"
            ),
        ],
    )
    def test_exists(self, data, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock(side_effect=data)
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act
        host_path.exists()

        # Assert
        print(fake_run_process.call_args_list)
        fake_run_process.assert_called_once_with(["ls", "-d", "a/b/c"])

    def test_exists__error(self, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock(
            side_effect=exceptions.FailedProcessError(["ls", "-d", "bla"]),
        )
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act / Assert
        with pytest.raises(exceptions.FailedProcessError):
            host_path.exists()

    def test_mkdir(self, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock()
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act
        host_path.mkdir()

        # Assert
        print(fake_run_process.call_args_list)
        fake_run_process.assert_called_once_with(["mkdir", "a/b/c"])

    def test_rename(self, monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock()
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b/c", connection=connection)

        # Act
        host_path.rename(PurePath("d/e"))

        # Assert
        print(fake_run_process.call_args_list)
        fake_run_process.assert_called_once_with(["mv", "a/b/c", "d/e"])

    @pytest.mark.parametrize(
        ("data", "expect"),
        [
            ("\n", []),
            ("c\nd\n", [PurePath("a/b/c"), PurePath("a/b/d")]),
        ],
    )
    def test_iterdir(self, data: str, expect: list[PurePath], monkeypatch: pytest.MonkeyPatch):
        # Arrange
        connection = Connection.from_url("/opt")
        fake_run_process = MagicMock(return_value=data)
        monkeypatch.setattr(connection, "run_process", fake_run_process)
        host_path = BackupHostPath("a/b", connection=connection)

        # Act
        result = host_path.iterdir()

        # Assert
        print(fake_run_process.call_args_list)
        fake_run_process.assert_called_once_with(["ls", "a/b"])

        assert all(isinstance(x, BackupHostPath) for x in result)
        assert set(result) == set(expect)


class TestSnapshot:
    def test_escape_path(self):
        # Arrange
        path = BackupHostPath("a/b/c", connection=MagicMock())
        expect = BackupHostPath("a!b!c", connection=MagicMock())

        # Act
        result = Snapshot.escape_path(path)

        # Assert
        assert result == expect

    def test_unescape_path(self):
        # Arrange
        path = BackupHostPath("a!b!c", connection=MagicMock())
        expect = BackupHostPath("a/b/c", connection=MagicMock())

        # Act
        result = Snapshot.unescape_path(path)

        # Assert
        assert result == expect

    def test_from_new(self):
        # Act
        result = Snapshot.from_new(
            name="yesterday_manual",
            base_path=BackupHostPath("a/b", connection=MagicMock()),
            subvolumes=[
                BackupHostPath("c/f", connection=MagicMock()),
                BackupHostPath("d", connection=MagicMock()),
                BackupHostPath("e", connection=MagicMock()),
            ],
        )

        # Assert
        assert result.subvolumes[0] == PurePath("c!f")

    def test_subvolumes_unescaped(self):
        # Arrange
        snapshot = Snapshot.from_new(
            name="yesterday_manual",
            base_path=BackupHostPath("a/b", connection=MagicMock()),
            subvolumes=[
                BackupHostPath("c/f", connection=MagicMock()),
                BackupHostPath("d", connection=MagicMock()),
                BackupHostPath("e", connection=MagicMock()),
            ],
        )

        # Act
        result = list(snapshot.subvolumes_unescaped)

        # Assert
        assert result[0] == PurePath("c/f")


class TestRetentionGroup:
    @pytest.mark.parametrize(
        ("name", "is_src", "expect"),
        [
            (
                "test",
                False,
                RetentionGroup(
                    name="test",
                    target_retention={"all": "4"},
                    is_source=False,
                ),
            ),
            (
                "idontexist",
                False,
                RetentionGroup(
                    name="idontexist",
                    target_retention={"all": "2"},
                    is_source=False,
                ),
            ),
            (
                "test",
                True,
                RetentionGroup(
                    name="test",
                    target_retention={"all": "3"},
                    is_source=True,
                ),
            ),
            (
                "idontexist",
                True,
                RetentionGroup(
                    name="idontexist",
                    target_retention={"all": "1"},
                    is_source=True,
                ),
            ),
        ],
    )
    def test_from_target(self, name: str, is_src: bool, expect: RetentionGroup, config: BaseConfig):
        # Act
        result = RetentionGroup.from_target(
            retention_name=name,
            target=config.backup_targets["localhost/home"],
            obsolete_snapshots=None,
            is_source=is_src,
        )

        # Assert
        print(result)
        assert result == expect


class TestChoiceSelector:
    @pytest.mark.parametrize(
        ("data", "expect"),
        [
            (["a/b", "a/c"], ["a/b", "a/c"]),
            ([], []),
            (["f"], []),
            (["a"], ["a/b", "a/c"]),
            (["."], ["a/b", "a/c", "b", "c", "d"]),
        ],
    )
    def test_choice_selector_resolve_target(self, data: list[str], expect: list[str]):
        # Arrange
        selector = ChoiceSelector(data)

        # Act
        result = selector.resolve_target(["a/b", "a/c", "b", "c", "d"])

        # Assert
        assert set(result) == set(expect)

    @pytest.mark.parametrize(
        ("data", "expect"),
        [
            (["alpha", "bravo"], ["alpha", "bravo"]),
            ([], []),
            (["ALL"], ["alpha", "bravo", "charlie"]),
        ],
    )
    def test_choice_selector_resolve_retention_name(self, data: list[str], expect: list[str]):
        # Arrange
        selector = ChoiceSelector(data)

        # Act
        result = selector.resolve_retention_name(
            [
                "2024-05-26-15-32-24_alpha",
                "2024-05-26-16-32-24_bravo",
                "2024-05-26-17-32-24_bravo",
                "2024-05-26-18-32-24_charlie",
                "2024-05-26-19-32-24_charlie",
                "2024-05-26-20-32-24_charlie",
            ]
        )

        # Assert
        assert set(result) == set(expect)
