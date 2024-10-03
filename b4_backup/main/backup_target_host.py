import contextlib
import logging
import shlex
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath
from typing import Generator, Iterable, Sequence

from b4_backup import exceptions
from b4_backup.config_schema import (
    BackupTarget,
    OnDestinationDirNotFound,
    SubvolumeBackupStrategy,
)
from b4_backup.main.connection import Connection, LocalConnection
from b4_backup.main.dataclass import BackupHostPath, ChoiceSelector, Snapshot
from b4_backup.utils import contains_path

log = logging.getLogger("b4_backup.main")


@dataclass
class BackupTargetHost(metaclass=ABCMeta):
    """
    Describes a host containing backups. Can be source and destination.

    Attributes:
        name: The name of the TargetHost
        target_config: The Config object describing this BackupTarget
        snapshot_dir: Path to the snapshots of this target on this host
        connection: Connection object to the host
    """

    name: str
    target_config: BackupTarget
    snapshot_dir: BackupHostPath
    connection: Connection

    @classmethod
    def from_source_host(
        cls,
        target_name: str,
        target_config: BackupTarget,
        connection: Connection,
    ) -> "SourceBackupTargetHost":
        """
        Create an instance for a backup source.

        Args:
            target_name: Name of the target
            target_config: Target config
            connection: Host connection

        Returns:
            BackupHost instance
        """
        target_snapshot_dir = (
            BackupTargetHost._mount_point(connection)
            / target_config.src_snapshot_dir
            / "snapshots"
            / target_name
        )

        return SourceBackupTargetHost(
            name=target_name,
            target_config=target_config,
            snapshot_dir=BackupHostPath(target_snapshot_dir, connection=connection),
            connection=connection,
        )

    @classmethod
    def from_destination_host(
        cls,
        target_name: str,
        target_config: BackupTarget,
        connection: Connection,
    ) -> "DestinationBackupTargetHost":
        """
        Create an instance for a backup destination.

        Args:
            target_name: Name of the target
            target_config: Target config
            connection: Host connection

        Returns:
            BackupHost instance
        """
        host = DestinationBackupTargetHost(
            name=target_name,
            target_config=target_config,
            snapshot_dir=BackupHostPath(
                connection.location / "snapshots" / target_name, connection=connection
            ),
            connection=connection,
        )

        if (
            target_config.if_dst_dir_not_found == OnDestinationDirNotFound.FAIL
            and not host.path().exists()
        ):
            raise exceptions.DestinationDirectoryNotFoundError(
                "Destination directory does not exist. B4 is configured to fail. Is the device mounted properly?"
            )

        return host

    @classmethod
    def _mount_point(cls, connection: Connection) -> BackupHostPath:
        result = connection.run_process(["mount"])

        possible_paths: list[PurePath] = []
        for line in result.split("\n"):
            if line == "":
                continue

            columns = line.split()
            path = PurePath(columns[2])

            if columns[4] != "btrfs" or not connection.location.is_relative_to(path):
                continue

            possible_paths.append(path)

        if len(possible_paths) == 0:
            raise exceptions.BtrfsPartitionNotFoundError(
                f"{connection.location} is not located on a valid btrfs partition"
            )

        return BackupHostPath(sorted(possible_paths)[-1], connection=connection)

    def mount_point(self) -> BackupHostPath:
        """
        Returns:
            the mount point of the target location.
        """
        return self._mount_point(self.connection)

    @property
    @abstractmethod
    def type(self) -> str:
        """
        Returns:
            if it's a source or destination host.
        """

    def subvolumes(self) -> list[BackupHostPath]:
        """
        Returns:
            A list of btrfs subvolumes.
        """
        mount_point = self.mount_point()

        result = self.connection.run_process(["btrfs", "subvolume", "list", str(mount_point)])
        result = result.replace("top level", "top_level")

        # Format looking like this per line:
        # ID 256 gen 621187 top_level 5 path my_data
        return sorted(
            [
                mount_point / value
                for line in result.split("\n")
                # Iterate two items at a time
                for key, value in zip(*[iter(line.split())] * 2)  # type: ignore
                if key == "path"
            ]
            + [mount_point]
        )

    def _group_subvolumes(
        self, subvolumes: Sequence[BackupHostPath], parent_dir: BackupHostPath
    ) -> dict[str, list[BackupHostPath]]:
        relevant_subvolumes = [
            x
            for x in subvolumes
            if x.is_relative_to(parent_dir) and len(x.relative_to(parent_dir).parts) >= 1
        ]

        result_dict: dict[str, list] = {}
        for subvol in relevant_subvolumes:
            group = subvol.relative_to(parent_dir)
            group_name = group.parts[0]
            group_subdir = group.relative_to(group_name)

            if group_name not in result_dict:
                result_dict[group_name] = []

            result_dict[group_name].append(group_subdir)

        return result_dict

    def snapshots(self) -> dict[str, Snapshot]:
        """
        Returns:
            All snapshots for that host/target.
        """
        return {
            k: Snapshot(
                name=k,
                subvolumes=v,
                base_path=self.snapshot_dir,
            )
            for k, v in self._group_subvolumes(
                self.subvolumes(),
                self.snapshot_dir,
            ).items()
        }

    def path(self, path: PurePath | str | None = None) -> BackupHostPath:
        """
        Create a BackupHostPath instance.

        Args:
            path: Pathlike object. If None, the connection location will be used

        Returns:
            BackupHostPath instance
        """
        if path is None:
            path = self.connection.location

        return BackupHostPath(path, connection=self.connection)

    def delete_snapshot(
        self,
        snapshot: Snapshot,
        subvolumes: list[BackupHostPath] | None = None,
    ) -> None:
        """
        Delete a snapshot.

        Args:
            snapshot: Snapshot to delete
            subvolumes: Subvolumes to delete. If None, all subvolumes are deleted
        """
        if subvolumes is None:
            subvolumes = snapshot.subvolumes

        for subvolume in snapshot.subvolumes:
            if subvolume not in subvolumes:
                continue

            subvolume_dir = snapshot.base_path / snapshot.name / subvolume

            log.info("Delete snapshot %s on %s", str(snapshot.name / subvolume), self.type)
            self.connection.run_process(["btrfs", "subvolume", "delete", str(subvolume_dir)])

        if subvolumes == snapshot.subvolumes:
            (snapshot.base_path / snapshot.name).rmdir()

    def _get_nearest_matching_snapshot(
        self,
        snapshot_name: str,
        src_group_names: set[str],
        dst_group_names: set[str],
    ) -> str | None:
        matching_groups = sorted(src_group_names & dst_group_names)

        if not matching_groups:
            return None

        return (
            [x for x in sorted(matching_groups, reverse=True) if x < snapshot_name]
            + [x for x in sorted(matching_groups) if x > snapshot_name]
        )[0]

    def _map_parent_snapshots(
        self, new_snapshot: Snapshot, parent_snapshot: Snapshot
    ) -> dict[PurePath, bool]:
        parent_snapshot_set = set(parent_snapshot.subvolumes)
        return {x: x in parent_snapshot_set for x in new_snapshot.subvolumes}

    @classmethod
    def _filter_subvolumes(
        cls, subvolumes: Iterable[BackupHostPath], search_paths: list[PurePath]
    ) -> Generator[BackupHostPath, None, None]:
        return (
            x
            for x in subvolumes
            if any(contains_path(x, search_path) for search_path in search_paths)
        )

    def source_subvolumes_from_snapshot(
        self, snapshot: Snapshot
    ) -> Generator[BackupHostPath, None, None]:
        """
        Retrieve subvolumes that are marked as source only and ignore from a snapshot.

        Args:
            snapshot: Snapshot to retrieve the subvolumes from

        Returns:
            Generator of subvolumes
        """
        return (
            Snapshot.escape_path(x)
            for x in self.filter_subvolumes_by_backup_strategy(
                snapshot.subvolumes_unescaped,
                {SubvolumeBackupStrategy.SOURCE_ONLY, SubvolumeBackupStrategy.IGNORE},
            )
        )

    def filter_subvolumes_by_backup_strategy(
        self,
        subvolumes: Iterable[BackupHostPath],
        backup_strategies: set[SubvolumeBackupStrategy],
    ) -> Generator[BackupHostPath, None, None]:
        """
        Retrieve subvolumes that are marked as source only from a snapshot.

        Args:
            subvolumes: Subvolumes to filter
            backup_strategies: Backup strategies to search for

        Returns:
            Generator of subvolumes
        """
        return self._filter_subvolumes(
            (self.path("/") / x for x in subvolumes),
            [
                PurePath(k)
                for k, v in self.target_config.subvolume_rules.items()
                if v.backup_strategy in backup_strategies
            ],
        )

    def _remove_source_subvolumes(self, snapshots: dict[str, Snapshot]) -> None:
        for snapshot in snapshots.values():
            for subvolume in list(self.source_subvolumes_from_snapshot(snapshot)):
                snapshot.subvolumes.remove(subvolume)

    def send_snapshot(
        self,
        destination: "BackupTargetHost",
        snapshot_name: str,
        send_con: LocalConnection = LocalConnection(PurePath()),
        incremental: bool = True,
    ) -> None:
        """
        Send a snapshot to the destination host.

        Args:
            destination: Destination host
            snapshot_name: snapshot to transmit
            send_con: Optional connection from where to send from
            incremental: Only send the difference from the nearest snapshot already sent
        """
        src_snapshots = self.snapshots()
        dst_snapshots = destination.snapshots()
        self._remove_source_subvolumes(src_snapshots)

        if snapshot_name in dst_snapshots:
            log.info("Snapshot already present at %s", destination.type)
            return

        if snapshot_name not in src_snapshots:
            raise exceptions.SnapshotNotFoundError(f"The snapshot {snapshot_name} does not exist.")

        snapshot = src_snapshots[snapshot_name]

        parent_snapshot_name = None
        if incremental:
            parent_snapshot_name = self._get_nearest_matching_snapshot(
                src_group_names=set(src_snapshots),
                dst_group_names=set(dst_snapshots),
                snapshot_name=snapshot_name,
            )

        snapshot_parent_mapping = None
        if parent_snapshot_name:
            log.info("Using incremental send based on snapshot: %s", parent_snapshot_name)
            parent_snapshot = src_snapshots[parent_snapshot_name]
            snapshot_parent_mapping = self._map_parent_snapshots(snapshot, parent_snapshot)

        (destination.snapshot_dir / snapshot_name).mkdir(parents=True)

        with send_con:
            for subvol in snapshot.subvolumes:
                parent_param = ""
                if (
                    parent_snapshot_name
                    and snapshot_parent_mapping is not None
                    and snapshot_parent_mapping[subvol] is True
                ):
                    parent_param = (
                        f" -p {shlex.quote(str(self.snapshot_dir / parent_snapshot_name / subvol))}"
                    )

                send_cmd = (
                    f"{self.connection.exec_prefix}btrfs send{parent_param}"
                    f" {shlex.quote(str(self.snapshot_dir / snapshot_name / subvol))}"
                )
                receive_cmd = (
                    f"{destination.connection.exec_prefix}btrfs receive"
                    f" {shlex.quote(str(destination.snapshot_dir / snapshot_name))}"
                )
                log.info(
                    "Sending snapshot: %s from %s to %s",
                    str(snapshot_name / subvol),
                    self.type,
                    destination.type,
                )
                send_con.run_process(["bash", "-c", f"{send_cmd} | {receive_cmd}"])


@dataclass
class SourceBackupTargetHost(BackupTargetHost):
    """Describes a source host containing backups. An extention of the generic BackupHost."""

    @property
    def type(self) -> str:
        """
        Returns:
            if it's a source or destination host.
        """
        return "source"

    def create_snapshot(self, snapshot_name: str) -> Snapshot:
        """
        Create a new snapshot for this target with the given name.

        Args:
            snapshot_name: Name of the snapshot.

        Returns:
            Instance of the newly created snapshot.
        """
        log.debug("Identify target subvolumes to backup")

        src_subvolumes = self.subvolumes()
        src_target_subvolumes = [
            self.path("/") / x.relative_to(self.connection.location)
            for x in src_subvolumes
            if x.is_relative_to(self.connection.location)
        ]

        for subvolume in list(
            self.filter_subvolumes_by_backup_strategy(
                src_target_subvolumes, {SubvolumeBackupStrategy.IGNORE}
            )
        ):
            src_target_subvolumes.remove(subvolume)

        if not src_target_subvolumes:
            raise exceptions.BtrfsSubvolumeNotFoundError(
                f"The target {self.name} does not contain any btrfs subvolumes"
            )

        snapshot = Snapshot.from_new(
            name=snapshot_name,
            subvolumes=src_target_subvolumes,
            base_path=self.snapshot_dir,
        )

        original_src_target_subvolumes = [
            self.connection.location / x for x in snapshot.subvolumes_unescaped
        ]
        new_src_target_snapshots = [
            self.snapshot_dir / snapshot.name / x for x in snapshot.subvolumes
        ]

        log.debug("Create snapshots")
        (snapshot.base_path / snapshot.name).mkdir(parents=True)

        for source_path, snapshot_path in zip(
            original_src_target_subvolumes, new_src_target_snapshots
        ):
            self.connection.run_process(
                ["btrfs", "subvolume", "snapshot", "-r", str(source_path), str(snapshot_path)]
            )

        return snapshot


@dataclass
class DestinationBackupTargetHost(BackupTargetHost):
    """Describes a destination host containing backups. An extention of the generic BackupHost."""

    @property
    def type(self) -> str:
        """
        Returns:
            if it's a source or destination host.
        """
        return "destination"


def host_generator(
    target_choice: ChoiceSelector,
    backup_targets: dict[str, BackupTarget],
    *,
    offline: bool = False,
) -> Generator[tuple[SourceBackupTargetHost, DestinationBackupTargetHost | None], None, None]:
    """
    Creates a generator containing connected TargetHosts for source and destination.

    Args:
        target_choice: A ChoiceSelector list of targets to be used
        backup_targets: A dict containing all targets available
        offline: If true, the destination host will be omitted

    Returns:
        A tuple containing source and destination TargetHosts
    """
    target_names = target_choice.resolve_target(backup_targets)

    for target_name in target_names:
        log.info("Backup target: %s", target_name)
        target = backup_targets[target_name]

        source = Connection.from_url(target.source)
        destination = contextlib.nullcontext()
        if target.destination and not offline:
            destination = Connection.from_url(target.destination)
        else:
            log.info("Skipped connection to destination host")

        with source as src_con, destination as dst_con:
            src_host = BackupTargetHost.from_source_host(
                target_name=target_name,
                target_config=target,
                connection=src_con,
            )

            dst_host = None
            if dst_con:
                dst_host = BackupTargetHost.from_destination_host(
                    target_name=target_name,
                    target_config=target,
                    connection=dst_con,
                )

            yield src_host, dst_host
