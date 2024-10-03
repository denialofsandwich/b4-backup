import textwrap
from pathlib import Path, PurePath
from unittest.mock import MagicMock, call

import pytest

from b4_backup import exceptions
from b4_backup.config_schema import BaseConfig
from b4_backup.main.backup_target_host import (
    BackupTargetHost,
    DestinationBackupTargetHost,
    SourceBackupTargetHost,
    host_generator,
)
from b4_backup.main.connection import LocalConnection
from b4_backup.main.dataclass import ChoiceSelector, Snapshot


class TestBackupTargetHost:
    def test_from_source_host(
        self,
        config: BaseConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        monkeypatch.setattr(BackupTargetHost, "_mount_point", MagicMock(return_value=Path("/mnt")))
        target_name = "localhost/home"

        # Act
        host = BackupTargetHost.from_source_host(
            target_name=target_name,
            target_config=config.backup_targets[target_name],
            connection=LocalConnection(Path()),
        )

        # Assert
        assert isinstance(host, SourceBackupTargetHost)
        assert host.snapshot_dir == Path("/mnt/.b4_backup/snapshots/localhost/home")

    def test_from_destination_host(
        self,
        config: BaseConfig,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        monkeypatch.setattr(BackupTargetHost, "_mount_point", MagicMock(return_value=Path("/mnt")))
        target_name = "localhost/home"

        # Act
        host = BackupTargetHost.from_destination_host(
            target_name=target_name,
            target_config=config.backup_targets[target_name],
            connection=LocalConnection(Path("/home")),
        )

        # Assert
        assert isinstance(host, DestinationBackupTargetHost)
        assert host.snapshot_dir == Path("/home/snapshots/localhost/home")

    def test_from_destination_host__error(self, config: BaseConfig):
        # Arrange
        target_name = "localhost/root"

        # Act / Assert
        with pytest.raises(exceptions.DestinationDirectoryNotFoundError):
            BackupTargetHost.from_destination_host(
                target_name=target_name,
                target_config=config.backup_targets[target_name],
                connection=LocalConnection(Path("/idontexist")),
            )

    def test_mount_point(
        self,
        dst_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        mount_result = textwrap.dedent(
            """
            /dev/sda1 on /boot type ext4 (rw,relatime)
            /dev/sda3 on / type btrfs (rw,relatime,discard=async,space_cache=v2,subvolid=5,subvol=/)
        """
        )
        monkeypatch.setattr(
            dst_host.connection, "run_process", MagicMock(return_value=mount_result)
        )

        # Act
        result = dst_host.mount_point()

        # Assert
        assert result == PurePath("/")

    def test_mount_point__error(
        self,
        dst_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        mount_result = textwrap.dedent(
            """
            /dev/sda1 on /boot type ext4 (rw,relatime)
            /dev/sda3 on /idontexist type btrfs (rw,relatime,discard=async,space_cache=v2,subvolid=5,subvol=/)
        """
        )
        monkeypatch.setattr(
            dst_host.connection, "run_process", MagicMock(return_value=mount_result)
        )

        # Act
        with pytest.raises(exceptions.BtrfsPartitionNotFoundError):
            dst_host.mount_point()

    def test_subvolumes(
        self,
        src_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        run_process_result = textwrap.dedent(
            """
            ID 256 gen 621187 top_level 5 path alpha/bravo
        """
        )
        monkeypatch.setattr(
            src_host.connection, "run_process", MagicMock(return_value=run_process_result)
        )
        monkeypatch.setattr(src_host, "mount_point", MagicMock(return_value=src_host.path("/opt")))

        # Act
        result = src_host.subvolumes()
        print(result)

        # Assert
        assert result == [PurePath("/opt"), PurePath("/opt/alpha/bravo")]

    def test_group_subvolumes(self, src_host: BackupTargetHost):
        # Arrange
        subvolumes = [
            src_host.path(x)
            for x in [
                "/opt/test",
                "/opt/test/alpha",
                "/opt/test/alpha/a",
                "/opt/test/bravo/a",
                "/opt/test/bravo/b",
                "/home",
            ]
        ]
        parent_dir = src_host.path("/opt/test")

        # Act
        result = src_host._group_subvolumes(subvolumes, parent_dir)
        print(result)

        # Assert
        assert result == {
            "alpha": [PurePath(), PurePath("a")],
            "bravo": [PurePath("a"), PurePath("b")],
        }

    def test_snapshots(
        self,
        src_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        subvolumes = [
            "/opt/.b4_backup/snapshots/localhost/home/alpha",
            "/opt/.b4_backup/snapshots/localhost/home/alpha/a",
            "/opt/.b4_backup/snapshots/localhost/home/alpha/b",
        ]
        monkeypatch.setattr(
            src_host, "subvolumes", MagicMock(return_value=[src_host.path(x) for x in subvolumes])
        )

        # Act
        result = src_host.snapshots()
        print(result)

        # Assert
        assert result == {
            "alpha": Snapshot(
                name="alpha",
                subvolumes=[
                    src_host.path("."),
                    src_host.path("a"),
                    src_host.path("b"),
                ],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            )
        }

    @pytest.mark.parametrize(
        ("test_input", "expect"),
        [
            (None, "/home"),
            ("/opt", "/opt"),
        ],
    )
    def test_path(self, src_host: BackupTargetHost, test_input, expect):
        # Act
        result = src_host.path(test_input)

        # Assert
        assert result == PurePath(expect)

    def test_delete_snapshot__full(
        self,
        src_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        snapshot = Snapshot(
            name="alpha",
            subvolumes=[
                src_host.path("."),
                src_host.path("a"),
                src_host.path("b"),
            ],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )

        fake_run_process = MagicMock()
        monkeypatch.setattr(src_host.connection, "run_process", fake_run_process)

        # Act
        src_host.delete_snapshot(snapshot)

        # Assert
        print(fake_run_process.call_args_list)
        assert fake_run_process.call_args_list == [
            call(
                ["btrfs", "subvolume", "delete", "/opt/.b4_backup/snapshots/localhost/home/alpha"]
            ),
            call(
                ["btrfs", "subvolume", "delete", "/opt/.b4_backup/snapshots/localhost/home/alpha/a"]
            ),
            call(
                ["btrfs", "subvolume", "delete", "/opt/.b4_backup/snapshots/localhost/home/alpha/b"]
            ),
            call(["rmdir", "/opt/.b4_backup/snapshots/localhost/home/alpha"]),
        ]

    def test_delete_snapshot__part(
        self,
        src_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        snapshot = Snapshot(
            name="alpha",
            subvolumes=[
                src_host.path("."),
                src_host.path("a"),
                src_host.path("b"),
            ],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )

        fake_run_process = MagicMock()
        monkeypatch.setattr(src_host.connection, "run_process", fake_run_process)

        # Act
        src_host.delete_snapshot(snapshot, [src_host.path("a")])

        # Assert
        assert fake_run_process.call_args_list == [
            call(
                ["btrfs", "subvolume", "delete", "/opt/.b4_backup/snapshots/localhost/home/alpha/a"]
            )
        ]

    @pytest.mark.parametrize(
        ("snapshot_name", "src_group_names", "dst_group_names", "expected_result"),
        [
            ("3", {"1", "2", "3"}, {"1", "2"}, "2"),
            ("3", {"1", "2", "3"}, {"4", "5"}, None),
            ("3", set(), set(), None),
            ("3", {"3", "4", "5"}, {"4", "5"}, "4"),
        ],
    )
    def test_get_nearest_matching_snapshot(
        self,
        src_host: BackupTargetHost,
        snapshot_name: str,
        src_group_names: set[str],
        dst_group_names: set[str],
        expected_result: str | None,
    ):
        # Act
        result = src_host._get_nearest_matching_snapshot(
            snapshot_name,
            src_group_names=src_group_names,
            dst_group_names=dst_group_names,
        )

        # Assert
        assert result == expected_result

    def test_map_snapshots(
        self,
        src_host: BackupTargetHost,
    ):
        # Arrange
        new_snapshot = Snapshot(
            name="alpha",
            subvolumes=[src_host.path(x) for x in ["", "b", "b/a"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )
        parent_snapshot = Snapshot(
            name="alpha",
            subvolumes=[src_host.path(x) for x in ["", "a", "b"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )

        # Act
        result = src_host._map_parent_snapshots(new_snapshot, parent_snapshot)

        # Assert
        assert result == {
            PurePath(): True,
            PurePath("b"): True,
            PurePath("b/a"): False,
        }

    def test_filter_subvolumes(self, src_host: SourceBackupTargetHost):
        # Arrange
        subvolumes = [
            src_host.path("/opt/bad/a/b"),
            src_host.path("/opt/mad"),
            src_host.path("/opt/alpha_bad"),
            src_host.path("/opt/alpha/a"),
            src_host.path("/opt/bravo/a"),
            src_host.path("/opt/charlie"),
        ]
        ignored_paths = [PurePath("alpha"), PurePath("bravo"), PurePath("charlie")]
        expect = [
            src_host.path("/opt/alpha/a"),
            src_host.path("/opt/bravo/a"),
            src_host.path("/opt/charlie"),
        ]

        # Act
        result = src_host._filter_subvolumes(subvolumes, ignored_paths)

        # Assert
        assert list(result) == expect

    def test_source_subvolumes_from_snapshot(self, src_host: BackupTargetHost):
        # Arrange
        snapshot = Snapshot(
            name="alpha_test",
            subvolumes=[src_host.path(x) for x in ["!", "!test"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )

        # Act
        result = src_host.source_subvolumes_from_snapshot(snapshot)

        # Assert
        assert list(result) == [src_host.path("!test")]

    def test_remove_source_subvolumes(self, src_host: BackupTargetHost):
        # Arrange
        snapshots = {
            "alpha_test": Snapshot(
                name="alpha_test",
                subvolumes=[src_host.path(x) for x in ["!", "!test"]],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
            "bravo_test": Snapshot(
                name="bravo_test",
                subvolumes=[src_host.path(x) for x in ["!", "!test"]],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
        }

        # Act
        src_host._remove_source_subvolumes(snapshots)

        # Assert
        assert snapshots == {
            "alpha_test": Snapshot(
                name="alpha_test",
                subvolumes=[src_host.path(x) for x in ["!"]],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
            "bravo_test": Snapshot(
                name="bravo_test",
                subvolumes=[src_host.path(x) for x in ["!"]],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
        }

    @pytest.mark.parametrize(
        ("snapshot_name", "incremental", "expect_src", "expect_dst", "expect_send"),
        [
            ("alpha", True, [], [], []),
            (
                "bravo",
                True,
                [],
                [call(["mkdir", "/opt/b4/snapshots/localhost/home/bravo", "-p"])],
                [
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send -p '/opt/.b4_backup/snapshots/localhost/home/alpha/!' '/opt/.b4_backup/snapshots/localhost/home/bravo/!' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send -p '/opt/.b4_backup/snapshots/localhost/home/alpha/!b' '/opt/.b4_backup/snapshots/localhost/home/bravo/!b' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send -p '/opt/.b4_backup/snapshots/localhost/home/alpha/!b!a' '/opt/.b4_backup/snapshots/localhost/home/bravo/!b!a' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                ],
            ),
            (
                "bravo",
                False,
                [],
                [call(["mkdir", "/opt/b4/snapshots/localhost/home/bravo", "-p"])],
                [
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send '/opt/.b4_backup/snapshots/localhost/home/bravo/!' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send '/opt/.b4_backup/snapshots/localhost/home/bravo/!b' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                    call(
                        [
                            "bash",
                            "-c",
                            "btrfs send '/opt/.b4_backup/snapshots/localhost/home/bravo/!b!a' | btrfs receive /opt/b4/snapshots/localhost/home/bravo",
                        ]
                    ),
                ],
            ),
        ],
    )
    def test_send_snapshot(
        self,
        src_host: BackupTargetHost,
        dst_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
        snapshot_name: str,
        incremental: bool,
        expect_src: list,
        expect_dst: list,
        expect_send: list,
    ):
        # Arrange
        send_con = LocalConnection(PurePath())
        fake_src_run_proc = MagicMock()
        fake_dst_run_proc = MagicMock()
        fake_send_run_proc = MagicMock()
        monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_proc)
        monkeypatch.setattr(dst_host.connection, "run_process", fake_dst_run_proc)
        monkeypatch.setattr(send_con, "run_process", fake_send_run_proc)

        monkeypatch.setattr(
            src_host,
            "snapshots",
            MagicMock(
                return_value={
                    "alpha": Snapshot(
                        name="alpha",
                        subvolumes=[src_host.path(x) for x in ["!", "!b", "!b!a"]],
                        base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                    ),
                    "bravo": Snapshot(
                        name="bravo",
                        subvolumes=[src_host.path(x) for x in ["!", "!b", "!b!a"]],
                        base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                    ),
                }
            ),
        )
        monkeypatch.setattr(
            dst_host,
            "snapshots",
            MagicMock(
                return_value={
                    "alpha": Snapshot(
                        name="alpha",
                        subvolumes=[src_host.path(x) for x in ["!", "!b", "!b!a"]],
                        base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                    ),
                }
            ),
        )

        # Act
        src_host.send_snapshot(
            destination=dst_host,
            snapshot_name=snapshot_name,
            send_con=send_con,
            incremental=incremental,
        )

        # Assert
        print(fake_src_run_proc.call_args_list)
        print(fake_dst_run_proc.call_args_list)
        print(fake_send_run_proc.call_args_list)
        assert fake_src_run_proc.call_args_list == expect_src
        assert fake_dst_run_proc.call_args_list == expect_dst
        assert fake_send_run_proc.call_args_list == expect_send

    def test_send_snapshot__error(
        self,
        src_host: BackupTargetHost,
        dst_host: BackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        monkeypatch.setattr(src_host, "snapshots", MagicMock(return_value={}))
        monkeypatch.setattr(dst_host, "snapshots", MagicMock(return_value={}))

        # Act / Assert
        with pytest.raises(exceptions.SnapshotNotFoundError):
            src_host.send_snapshot(dst_host, "idontexist")


class TestSourceBackupTargetHost:
    def test_type(self, src_host: SourceBackupTargetHost):
        # Act
        result = src_host.type

        # Assert
        assert result == "source"

    def test_create_snapshot(
        self,
        src_host: SourceBackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        subvolumes = [
            "/home",
            "/home/test/.steam",
            "/home/test/ignored/subvol",
            "/home/test/pictures",
        ]
        fake_src_run_proc = MagicMock()
        monkeypatch.setattr(
            src_host, "subvolumes", MagicMock(return_value=[src_host.path(x) for x in subvolumes])
        )
        monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_proc)

        # Act
        result = src_host.create_snapshot("1")

        # Assert
        assert fake_src_run_proc.call_args_list == [
            call(["mkdir", "/opt/.b4_backup/snapshots/localhost/home/1", "-p"]),
            call(
                [
                    "btrfs",
                    "subvolume",
                    "snapshot",
                    "-r",
                    "/home",
                    "/opt/.b4_backup/snapshots/localhost/home/1/!",
                ]
            ),
            call(
                [
                    "btrfs",
                    "subvolume",
                    "snapshot",
                    "-r",
                    "/home/test/.steam",
                    "/opt/.b4_backup/snapshots/localhost/home/1/!test!.steam",
                ]
            ),
            call(
                [
                    "btrfs",
                    "subvolume",
                    "snapshot",
                    "-r",
                    "/home/test/pictures",
                    "/opt/.b4_backup/snapshots/localhost/home/1/!test!pictures",
                ]
            ),
        ]
        assert result == Snapshot(
            name="1",
            subvolumes=[
                src_host.path("!"),
                src_host.path("!test!.steam"),
                src_host.path("!test!pictures"),
            ],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        )

    def test_create_snapshot__error(
        self,
        src_host: SourceBackupTargetHost,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Arrange
        subvolumes = []
        fake_src_run_proc = MagicMock()
        monkeypatch.setattr(
            src_host, "subvolumes", MagicMock(return_value=[src_host.path(x) for x in subvolumes])
        )
        monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_proc)

        # Act
        with pytest.raises(exceptions.BtrfsSubvolumeNotFoundError):
            src_host.create_snapshot("1")


class TestDestinationBackupTargetHost:
    def test_type(self, dst_host: DestinationBackupTargetHost):
        # Act
        result = dst_host.type

        # Assert
        assert result == "destination"


def test_host_generator(config: BaseConfig, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(BackupTargetHost, "_mount_point", MagicMock(return_value=Path("/mnt")))
    target_choice = ChoiceSelector(["localhost/mnt"])

    # Act
    result = list(host_generator(target_choice, config.backup_targets))

    # Assert
    print(result)
    assert len(result) == 1
    assert isinstance(result[0][0], SourceBackupTargetHost)
    assert isinstance(result[0][1], DestinationBackupTargetHost)


def test_host_generator__offline(config: BaseConfig, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(BackupTargetHost, "_mount_point", MagicMock(return_value=Path("/mnt")))
    target_choice = ChoiceSelector(["localhost/mnt"])

    # Act
    result = list(host_generator(target_choice, config.backup_targets, offline=True))

    # Assert
    print(result)
    assert len(result) == 1
    assert isinstance(result[0][0], SourceBackupTargetHost)
    assert result[0][1] is None
