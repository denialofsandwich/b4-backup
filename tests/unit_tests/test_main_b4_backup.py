from pathlib import PurePath
from unittest.mock import MagicMock, call, patch

import arrow
import pytest

from b4_backup import exceptions
from b4_backup.config_schema import TargetRestoreStrategy
from b4_backup.main.b4_backup import B4Backup
from b4_backup.main.backup_target_host import (
    BackupTargetHost,
    DestinationBackupTargetHost,
    SourceBackupTargetHost,
)
from b4_backup.main.dataclass import (
    BackupHostPath,
    ChoiceSelector,
    RetentionGroup,
    Snapshot,
)


def _parse_dates(dates: list[str]) -> list[arrow.Arrow]:
    return [arrow.get(x.split("_")[0], B4Backup._timestamp_fmt) for x in dates]


@pytest.mark.parametrize(("use_dst_host"), [True, False])
def test_backup(use_dst_host: bool, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_host = MagicMock()
    fake_dst_host = MagicMock()
    monkeypatch.setattr(b4_backup, "clean", MagicMock())

    # Act
    b4_backup.backup(fake_src_host, fake_dst_host if use_dst_host else None, "alpha_manual")

    # Assert
    assert fake_src_host.create_snapshot.called
    assert fake_src_host.send_snapshot.called is use_dst_host


def test_restore__rollback():
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_rollback_replace = MagicMock()
    b4_backup._rollback_replace = fake_rollback_replace

    # Act
    b4_backup.restore(
        MagicMock(),
        MagicMock(),
        "REPLACE",
        TargetRestoreStrategy.REPLACE,
    )

    # Assert
    assert fake_rollback_replace.called


def test_restore__safe():
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_restore_safe = MagicMock()
    b4_backup._restore_safe = fake_restore_safe

    # Act
    b4_backup.restore(
        MagicMock(),
        MagicMock(),
        "alpha",
        TargetRestoreStrategy.SAFE,
    )

    # Assert
    assert fake_restore_safe.called


def test_restore__replace():
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_restore_replace = MagicMock()
    b4_backup._restore_replace = fake_restore_replace

    # Act
    b4_backup.restore(
        MagicMock(),
        MagicMock(),
        "alpha",
        TargetRestoreStrategy.REPLACE,
    )

    # Assert
    assert fake_restore_replace.called


def test_restore__error():
    # Arrange
    b4_backup = B4Backup("UTC")

    # Act / Assert
    with pytest.raises(exceptions.SnapshotNotFoundError):
        b4_backup.restore(
            MagicMock(),
            MagicMock(),
            "REPLACE",
            TargetRestoreStrategy.SAFE,
        )


@patch("b4_backup.main.b4_backup.B4Backup.clean")
def test_sync(fake_clean: MagicMock):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_host = MagicMock()
    fake_dst_host = MagicMock()
    fake_src_host.snapshots = MagicMock(return_value={"alpha": 1})
    fake_dst_host.snapshots = MagicMock(return_value={})

    # Act
    b4_backup.sync(fake_src_host, fake_dst_host)

    # Assert
    assert fake_clean.call_count == 2
    assert fake_src_host.send_snapshot.call_count == 1


def test_clean(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(b4_backup, "_clean_target", MagicMock())
    monkeypatch.setattr(b4_backup, "_clean_replace", MagicMock())
    monkeypatch.setattr(b4_backup, "_clean_empty_dirs", MagicMock())

    # Act
    b4_backup.clean(src_host)

    # Assert
    assert b4_backup._clean_target.called is True  # type: ignore
    assert b4_backup._clean_replace.called is True  # type: ignore


def test_delete(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_delete_snapshot = MagicMock()
    monkeypatch.setattr(src_host, "delete_snapshot", fake_delete_snapshot)
    monkeypatch.setattr(
        src_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[src_host.path("!")],
                    base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in ["alpha_test", "beta_test", "gamma_manual"]
            }
        ),
    )

    # Act
    b4_backup.delete(src_host, "alpha_test")

    # Assert
    assert fake_delete_snapshot.called is True


def test_delete__error(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_delete_snapshot = MagicMock()
    monkeypatch.setattr(src_host, "delete_snapshot", fake_delete_snapshot)
    monkeypatch.setattr(src_host, "snapshots", MagicMock(return_value={}))

    # Act
    b4_backup.delete(src_host, "alpha_test")

    # Assert
    assert fake_delete_snapshot.called is False


def test_delete_all(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    retention_name_choice = ChoiceSelector(["test"])
    b4_backup = B4Backup("UTC")
    fake_delete_snapshot = MagicMock()
    monkeypatch.setattr(src_host, "delete_snapshot", fake_delete_snapshot)
    monkeypatch.setattr(
        src_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[src_host.path("!")],
                    base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in ["alpha_test", "beta_test", "gamma_manual"]
            }
        ),
    )

    # Act
    b4_backup.delete_all(src_host, retention_name_choice)

    # Assert
    print(fake_delete_snapshot.call_args_list)
    assert [x.args[0].name for x in fake_delete_snapshot.call_args_list] == [
        "alpha_test",
        "beta_test",
    ]


def test_restore_replace(
    src_host: SourceBackupTargetHost,
    dst_host: DestinationBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(b4_backup, "_restore_safe", MagicMock())
    monkeypatch.setattr(b4_backup, "_remove_target", MagicMock())
    monkeypatch.setattr(b4_backup, "_restore_snapshot", MagicMock())
    fake_clean_replace = MagicMock()
    monkeypatch.setattr(b4_backup, "_clean_replace", fake_clean_replace)
    monkeypatch.setattr(
        src_host,
        "snapshots",
        MagicMock(
            return_value={
                "alpha": Snapshot(
                    name="alpha",
                    subvolumes=[src_host.path("!"), src_host.path("!test")],
                    base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                ),
            }
        ),
    )

    # Act
    b4_backup._restore_replace(src_host, dst_host, "alpha")

    # Assert
    assert fake_clean_replace.called is True


@pytest.mark.parametrize(("use_dst_host"), [True, False])
def test_restore_safe(
    src_host: SourceBackupTargetHost,
    dst_host: DestinationBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
    use_dst_host: bool,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(src_host, "snapshots", MagicMock(return_value={"alpha"}))
    monkeypatch.setattr(dst_host, "send_snapshot", MagicMock())

    # Act
    b4_backup._restore_safe(
        src_host,
        dst_host if use_dst_host else None,
        "alpha",
    )


def test_restore_safe__error(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(src_host, "snapshots", MagicMock(return_value={}))

    # Act
    with pytest.raises(exceptions.SnapshotNotFoundError):
        b4_backup._restore_safe(src_host, None, "alpha")


def test_rollback_replace(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    monkeypatch.setattr(
        BackupTargetHost, "_mount_point", MagicMock(return_value=src_host.path("/opt"))
    )
    monkeypatch.setattr(
        BackupHostPath,
        "iterdir",
        MagicMock(
            return_value=[
                src_host.path("2023-08-07-22-30-00"),
            ]
        ),
    )
    monkeypatch.setattr(b4_backup, "_remove_target", MagicMock())
    monkeypatch.setattr(b4_backup, "_clean_replace", MagicMock())

    # Act
    b4_backup._rollback_replace(src_host)

    # Assert
    print(fake_src_run_process.call_args_list)
    assert fake_src_run_process.call_args_list == [
        call(["mkdir", "/opt/.b4_backup/replace/localhost/home", "-p"]),
        call(["mv", "2023-08-07-22-30-00", "/home"]),
    ]


def test_rollback_replace__error(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    monkeypatch.setattr(
        BackupTargetHost, "_mount_point", MagicMock(return_value=src_host.path("/opt"))
    )
    monkeypatch.setattr(BackupHostPath, "iterdir", MagicMock(return_value=[]))

    # Act / Assert
    with pytest.raises(exceptions.SnapshotNotFoundError):
        b4_backup._rollback_replace(src_host)


@pytest.mark.parametrize(
    ("exists", "expect"),
    [
        (False, None),
        (True, "/opt/.b4_backup/replace/localhost/home/alpha"),
    ],
)
def test_remove_target(
    src_host: SourceBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
    exists: bool,
    expect: str | None,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    monkeypatch.setattr(BackupHostPath, "exists", MagicMock(return_value=exists))
    monkeypatch.setattr(
        BackupTargetHost, "_mount_point", MagicMock(return_value=src_host.path("/opt"))
    )
    monkeypatch.setattr(b4_backup, "generate_snapshot_name", MagicMock(return_value="alpha"))

    # Act
    result = b4_backup._remove_target(src_host)

    # Assert
    print(fake_src_run_process.call_args_list)
    assert result == (src_host.path(expect) if expect else None)
    assert fake_src_run_process.call_args_list == (
        [
            call(["mkdir", "/opt/.b4_backup/replace/localhost/home", "-p"]),
            call(["mv", "/home", "/opt/.b4_backup/replace/localhost/home/alpha"]),
        ]
        if expect
        else []
    )


@pytest.mark.parametrize(
    ("name", "expect"),
    [
        ("manual", "2023-08-07-22-30-00_manual"),
        (None, "2023-08-07-22-30-00"),
    ],
)
def test_generate_snapshot_name(
    monkeypatch: pytest.MonkeyPatch,
    name: str | None,
    expect: str,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-22-30-00",
                B4Backup._timestamp_fmt,
            )
        ),
    )

    # Act
    result = b4_backup.generate_snapshot_name(name)

    # Assert
    assert result == expect


def test_restore_snapshot(src_host: SourceBackupTargetHost, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    fake_create_fallback_subvolume = MagicMock()
    monkeypatch.setattr(b4_backup, "_create_fallback_subvolume", fake_create_fallback_subvolume)
    snapshot = Snapshot(
        name="alpha",
        subvolumes=[src_host.path("!"), src_host.path("!test")],
        base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
    )

    # Act
    b4_backup._restore_snapshot(src_host, snapshot)

    # Assert
    print(fake_src_run_process.call_args_list)
    assert fake_src_run_process.call_args_list == [
        call(["mkdir", "/", "-p"]),
        call(["rmdir", "/home"]),
        call(["mkdir", "/", "-p"]),
        call(
            [
                "btrfs",
                "subvolume",
                "snapshot",
                "/opt/.b4_backup/snapshots/localhost/home/alpha/!",
                "/home",
            ]
        ),
        call(["rmdir", "/home/test"]),
        call(["mkdir", "/home", "-p"]),
        call(
            [
                "btrfs",
                "subvolume",
                "snapshot",
                "/opt/.b4_backup/snapshots/localhost/home/alpha/!test",
                "/home/test",
            ]
        ),
    ]
    assert [x.args[1] for x in fake_create_fallback_subvolume.call_args_list] == [
        PurePath("/"),
        PurePath("/test"),
        PurePath("/new"),
        PurePath("/keep"),
    ]


@pytest.mark.parametrize(
    ("subvolume_path", "existing_path", "exists", "expect"),
    [
        (
            PurePath("/new"),
            None,
            [False],
            [
                call(["mkdir", "/home", "-p"]),
                call(["btrfs", "subvolume", "create", "/home/new"]),
            ],
        ),
        (
            PurePath("/keep"),
            None,
            [False],
            [
                call(["mkdir", "/home", "-p"]),
                call(["btrfs", "subvolume", "create", "/home/keep"]),
            ],
        ),
        (
            PurePath("/keep"),
            PurePath("/opt/old"),
            [False, False],
            [
                call(["mkdir", "/home", "-p"]),
                call(["btrfs", "subvolume", "create", "/home/keep"]),
            ],
        ),
        (
            PurePath("/keep"),
            PurePath("/opt/old"),
            [False, True],
            [
                call(["mkdir", "/home", "-p"]),
                call(["mv", "/opt/old/keep", "/home/keep"]),
            ],
        ),
        (
            PurePath("/keep"),
            PurePath("/opt/old"),
            [True],
            [],
        ),
        (
            PurePath("/test"),
            PurePath("/opt/old"),
            [False, True],
            [call(["mkdir", "/home", "-p"])],
        ),
    ],
)
def test_create_fallback_subvolume(
    src_host: SourceBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
    subvolume_path: PurePath,
    existing_path: PurePath | None,
    exists: list[bool],
    expect: list,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    monkeypatch.setattr(BackupHostPath, "exists", MagicMock(side_effect=exists))

    # Act
    b4_backup._create_fallback_subvolume(
        src_host,
        subvolume_path,
        src_host.path(existing_path) if existing_path else None,
    )

    # Assert
    print(fake_src_run_process.call_args_list)
    assert fake_src_run_process.call_args_list == expect


@pytest.mark.parametrize(
    ("src_subvolumes", "dst_subvolumes", "use_dst_host", "src_expect", "dst_expect"),
    [
        (
            [
                "2023-08-07-22-15-00_test_clean",
                "2023-08-07-22-00-00_test_clean",
            ],
            [
                "2023-08-07-22-15-00_test_clean",
                "2023-08-07-22-00-00_test_clean",
                "2023-08-07-21-00-00_test_clean",
            ],
            True,
            [],
            [
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-22-00-00_test_clean/!",
                    ]
                ),
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-22-00-00_test_clean/!test",
                    ]
                ),
                call(
                    [
                        "rmdir",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-22-00-00_test_clean",
                    ]
                ),
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-21-00-00_test_clean/!test",
                    ]
                ),
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-22-15-00_test_clean/!test",
                    ]
                ),
            ],
        ),
        (
            [
                "2023-08-07-22-15-00_test_clean",
                "2023-08-07-22-00-00_test_clean",
                "2023-08-07-21-15-00_test_clean",
                "2023-08-07-21-00-00_test_clean",
            ],
            [],
            False,
            [
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-21-00-00_test_clean/!",
                    ]
                ),
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-21-00-00_test_clean/!test",
                    ]
                ),
                call(
                    [
                        "rmdir",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-21-00-00_test_clean",
                    ]
                ),
                call(
                    [
                        "btrfs",
                        "subvolume",
                        "delete",
                        "/opt/.b4_backup/snapshots/localhost/home/2023-08-07-21-15-00_test_clean/!test",
                    ]
                ),
            ],
            [],
        ),
    ],
)
def test_clean_target(
    src_host: SourceBackupTargetHost,
    dst_host: DestinationBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
    src_subvolumes: list[str],
    dst_subvolumes: list[str],
    use_dst_host: bool,
    src_expect: list,
    dst_expect: list,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    retention_name_choice = ChoiceSelector(["test_clean"])
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-22-30-00",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    fake_src_run_process = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_process)
    fake_dst_run_process = MagicMock()
    monkeypatch.setattr(dst_host.connection, "run_process", fake_dst_run_process)
    monkeypatch.setattr(
        src_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[src_host.path(x) for x in ["!", "!test"]],
                    base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in src_subvolumes
            }
        ),
    )
    monkeypatch.setattr(
        dst_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[dst_host.path(x) for x in ["!", "!test"]],
                    base_path=dst_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in dst_subvolumes
            }
        ),
    )

    # Act
    b4_backup._clean_target(
        src_host,
        dst_host if use_dst_host else None,
        retention_name_choice,
    )

    # Assert
    print(fake_src_run_process.call_args_list)
    print(fake_dst_run_process.call_args_list)
    assert fake_src_run_process.call_args_list == src_expect
    assert fake_dst_run_process.call_args_list == dst_expect


def test_apply_retention(
    src_host: SourceBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-22-30-00",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    monkeypatch.setattr(
        src_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[src_host.path(x) for x in ["!", "!test"]],
                    base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in [
                    "2023-08-07-22-00-00_auto",
                    "2023-08-07-21-00-00_auto",
                    "2023-08-07-20-00-00_auto",
                ]
            }
        ),
    )
    fake_src_delete_snapshots = MagicMock()
    monkeypatch.setattr(src_host, "delete_snapshot", fake_src_delete_snapshots)

    # Act
    b4_backup._apply_retention(
        src_host,
        [
            RetentionGroup(
                name="auto",
                target_retention={"all": "1"},
                is_source=True,
            ),
            RetentionGroup(
                name="auto",
                target_retention={"all": "3"},
                is_source=False,
                obsolete_snapshots={"2023-08-07-20-00-00_auto"},
            ),
        ],
    )

    # Assert
    print(fake_src_delete_snapshots.call_args_list)
    assert fake_src_delete_snapshots.call_args_list == [
        call(
            Snapshot(
                name="2023-08-07-20-00-00_auto",
                subvolumes=[src_host.path("!"), src_host.path("!test")],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            )
        ),
        call(
            Snapshot(
                name="2023-08-07-21-00-00_auto",
                subvolumes=[src_host.path("!"), src_host.path("!test")],
                base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
            subvolumes=[src_host.path("!test")],
        ),
    ]


def test_apply_retention__destination(
    dst_host: DestinationBackupTargetHost,
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-22-30-00",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    monkeypatch.setattr(
        dst_host,
        "snapshots",
        MagicMock(
            return_value={
                x: Snapshot(
                    name=x,
                    subvolumes=[dst_host.path(x) for x in ["!", "!test"]],
                    base_path=dst_host.path("/opt/.b4_backup/snapshots/localhost/home"),
                )
                for x in [
                    "2023-08-07-22-00-00_auto",
                    "2023-08-07-21-00-00_auto",
                    "2023-08-07-20-00-00_auto",
                ]
            }
        ),
    )
    fake_src_delete_snapshots = MagicMock()
    monkeypatch.setattr(dst_host, "delete_snapshot", fake_src_delete_snapshots)

    # Act
    b4_backup._apply_retention(
        dst_host,
        [
            RetentionGroup(
                name="auto",
                target_retention={"all": "2"},
                is_source=False,
            ),
        ],
    )

    # Assert
    print(fake_src_delete_snapshots.call_args_list)
    assert fake_src_delete_snapshots.call_args_list == [
        call(
            Snapshot(
                name="2023-08-07-20-00-00_auto",
                subvolumes=[dst_host.path("!"), dst_host.path("!test")],
                base_path=dst_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            )
        ),
        call(
            Snapshot(
                name="2023-08-07-21-00-00_auto",
                subvolumes=[dst_host.path("!"), dst_host.path("!test")],
                base_path=dst_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
            subvolumes=[dst_host.path("!test")],
        ),
        call(
            Snapshot(
                name="2023-08-07-22-00-00_auto",
                subvolumes=[dst_host.path("!"), dst_host.path("!test")],
                base_path=dst_host.path("/opt/.b4_backup/snapshots/localhost/home"),
            ),
            subvolumes=[dst_host.path("!test")],
        ),
    ]


def test_filter_snapshots(src_host: SourceBackupTargetHost):
    # Arrange
    b4_backup = B4Backup("UTC")
    snapshots = {
        "2023-08-07-22-59-37_manual": Snapshot(
            name="2023-08-07-22-59-37_manual",
            subvolumes=[src_host.path(x) for x in ["", "b"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
        "2023-08-07-22-59-37_auto": Snapshot(
            name="2023-08-07-22-59-37_auto",
            subvolumes=[src_host.path(x) for x in ["", "b", "b/a"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
    }

    # Act
    result = b4_backup._filter_snapshots(snapshots, ["auto"])

    # Assert
    assert result == {
        "2023-08-07-22-59-37_auto": Snapshot(
            name="2023-08-07-22-59-37_auto",
            subvolumes=[src_host.path(x) for x in ["", "b", "b/a"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
    }


def test_extract_retention_name():
    # Arrange
    b4_backup = B4Backup("UTC")

    # Act
    result = b4_backup._extract_retention_name("2023-08-07-22-59-37_auto")

    # Assert
    assert result == "auto"


@pytest.mark.parametrize(
    ("replace_list", "expect"),
    [
        (
            ["2023-08-07-22-59-37", "2023-08-05-22-59-37", "2023-07-07-22-59-37"],
            ["2023-08-05-22-59-37", "2023-07-07-22-59-37"],
        ),
        ([], []),
    ],
)
def test_clean_replace(
    monkeypatch: pytest.MonkeyPatch,
    src_host: SourceBackupTargetHost,
    replace_list: list[str],
    expect: list[str],
):
    # Arrange
    b4_backup = B4Backup("UTC")
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-23-59-37",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    monkeypatch.setattr(src_host.connection, "run_process", MagicMock())
    monkeypatch.setattr(
        BackupTargetHost, "_mount_point", MagicMock(return_value=src_host.path("/opt"))
    )
    monkeypatch.setattr(
        BackupHostPath,
        "iterdir",
        MagicMock(return_value=[src_host.path(x) for x in replace_list]),
    )
    fake_src_rem_repl_targets = MagicMock()
    monkeypatch.setattr(b4_backup, "_remove_replaced_targets", fake_src_rem_repl_targets)

    # Act
    b4_backup._clean_replace(src_host)

    # Assert
    assert [str(x.args[1]) for x in fake_src_rem_repl_targets.call_args_list] == expect


@pytest.mark.parametrize(("use_dst_host"), [True, False])
def test_clean_empty_dirs(use_dst_host: bool):
    # Arrange
    b4_backup = B4Backup("UTC")
    fake_src_host = MagicMock()
    fake_dst_host = MagicMock()

    # Act
    b4_backup._clean_empty_dirs(fake_src_host, fake_dst_host if use_dst_host else None)

    # Assert
    assert fake_src_host.remove_empty_dirs.called
    assert fake_dst_host.remove_empty_dirs.called == use_dst_host


def test_remove_replaced_targets(
    monkeypatch: pytest.MonkeyPatch,
    src_host: SourceBackupTargetHost,
):
    # Arrange
    fake_src_run_proc = MagicMock()
    monkeypatch.setattr(src_host.connection, "run_process", fake_src_run_proc)
    monkeypatch.setattr(
        src_host,
        "subvolumes",
        MagicMock(return_value=[src_host.path(x) for x in ["/test/a", "/test/b", "/test/a/b"]]),
    )
    b4_backup = B4Backup("UTC")

    # Act
    b4_backup._remove_replaced_targets(src_host, PurePath("/test"))

    # Assert
    assert fake_src_run_proc.call_args_list == [
        call(["btrfs", "subvolume", "delete", "/test/a/b"]),
        call(["btrfs", "subvolume", "delete", "/test/b"]),
        call(["btrfs", "subvolume", "delete", "/test/a"]),
    ]


def test_transpose_snapshot_subvolumes(src_host: BackupTargetHost):
    # Arrange
    snapshots = {
        "alpha": Snapshot(
            name="alpha",
            subvolumes=[src_host.path(x) for x in ["", "b"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
        "beta": Snapshot(
            name="beta",
            subvolumes=[src_host.path(x) for x in ["", "b", "b/a"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
        "gamma": Snapshot(
            name="gamma",
            subvolumes=[src_host.path(x) for x in ["", "b", "b/a", "c"]],
            base_path=src_host.path("/opt/.b4_backup/snapshots/localhost/home"),
        ),
    }
    b4_backup = B4Backup("UTC")

    # Act
    result = b4_backup._transpose_snapshot_subvolumes(snapshots)
    print(result)

    # Assert
    assert result == {
        src_host.path(""): {"alpha", "beta", "gamma"},
        src_host.path("b"): {"alpha", "beta", "gamma"},
        src_host.path("b/a"): {"beta", "gamma"},
        src_host.path("c"): {"gamma"},
    }


def test_retained_snapshots(monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-23-59-37",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    b4_backup = B4Backup("UTC")
    snapshots = {
        "2023-07-07-22-59-37_auto",
        "2023-08-05-22-59-37_auto",
        "2023-08-06-22-59-37_auto",
        "2023-08-07-20-11-37_auto",
        "2023-08-07-20-58-47_auto",
        "2023-08-07-21-03-08_auto",
        "2023-08-07-21-07-33_auto",
        "2023-08-07-21-10-49_auto",
        "2023-08-07-21-11-21_auto",
        "2023-08-07-22-59-21_auto",
        "2023-08-07-22-59-37_auto",
        "2023-08-07-22-59-37_manual",
    }

    # Act
    result = b4_backup._retained_snapshots(
        snapshots,
        {
            "1hour": "1day",
            "1day": "1week",
        },
        "auto",
        ignored_snapshots={"2023-08-07-22-59-37_auto"},
    )

    print(result)
    # Assert
    assert result == {
        "2023-08-05-22-59-37_auto",
        "2023-08-06-22-59-37_auto",
        "2023-08-07-20-58-47_auto",
        "2023-08-07-21-11-21_auto",
    }


@pytest.mark.parametrize(
    ("interval", "duration", "expect"),
    [
        ("1seconds", "1minutes", []),
        ("1hours", "1days", ["2023-08-07-22-59-37", "2023-08-07-21-11-21", "2023-08-07-20-58-47"]),
        (
            "1days",
            "forever",
            ["2023-08-07-22-59-37", "2023-07-07-22-59-37"],
        ),
        (
            "all",
            "forever",
            [
                "2023-08-07-22-59-37",
                "2023-08-07-22-59-21",
                "2023-08-07-21-11-21",
                "2023-08-07-21-10-49",
                "2023-08-07-21-07-33",
                "2023-08-07-21-03-08",
                "2023-08-07-20-58-47",
                "2023-08-07-20-11-37",
                "2023-07-07-22-59-37",
            ],
        ),
        (
            "all",
            "2",
            [
                "2023-08-07-22-59-37",
                "2023-08-07-22-59-21",
            ],
        ),
    ],
)
def test_apply_retention_rule(
    interval: str,
    duration: str,
    expect: list[str],
    monkeypatch: pytest.MonkeyPatch,
):
    # Arrange
    monkeypatch.setattr(
        arrow,
        "utcnow",
        MagicMock(
            return_value=arrow.get(
                "2023-08-07-23-59-37",
                B4Backup._timestamp_fmt,
            )
        ),
    )
    b4_backup = B4Backup("UTC")
    dates = [
        "2023-07-07-22-59-37_auto",
        "2023-08-07-20-11-37_auto",
        "2023-08-07-20-58-47_auto",
        "2023-08-07-21-03-08_auto",
        "2023-08-07-21-07-33_auto",
        "2023-08-07-21-10-49_auto",
        "2023-08-07-21-11-21_auto",
        "2023-08-07-22-59-21_auto",
        "2023-08-07-22-59-37_auto",
    ]

    # Act
    result = b4_backup._apply_retention_rule(interval, duration, _parse_dates(dates))

    # Assert
    print(result)

    assert result == _parse_dates(expect)


@pytest.mark.parametrize(
    ("timebox", "is_interval", "expect"),
    [
        ("4days", True, (4, "days")),
        ("4days", False, (4, "days")),
        ("all", True, (0, "all")),
        ("forever", False, (0, "forever")),
        ("1year", False, (1, "years")),
        ("5weeks", False, (5, "weeks")),
        ("5", False, (5, None)),
    ],
)
def test_timebox_str_extract__success(
    timebox: str, is_interval: bool, expect: tuple[int, str | None]
):
    # Arrange
    b4_backup = B4Backup("UTC")

    # Act
    result = b4_backup._timebox_str_extract(timebox, is_interval=is_interval)

    # Assert
    assert result == expect


@pytest.mark.parametrize(
    ("timebox", "is_interval"),
    [("what4", True), ("all", False), ("forever", True)],
)
def test_timebox_str_extract__error(timebox: str, is_interval: bool):
    # Arrange
    b4_backup = B4Backup("UTC")

    # Act / Assert
    with pytest.raises(exceptions.InvalidRetentionRuleError):
        b4_backup._timebox_str_extract(timebox, is_interval=is_interval)
