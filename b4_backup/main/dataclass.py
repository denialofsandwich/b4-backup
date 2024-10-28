from dataclasses import dataclass, field
from os import PathLike
from pathlib import PurePath, PurePosixPath
from typing import TYPE_CHECKING, Generator, Iterable

from b4_backup import exceptions
from b4_backup.config_schema import DEFAULT, BackupTarget

if TYPE_CHECKING:  # pragma: no cover
    from b4_backup.main.connection import Connection


class BackupHostPath(PurePosixPath):
    """Represents a path for a Connection."""

    def __init__(self, *segments: str | PathLike[str], connection: "Connection"):
        """
        Args:
            segments: segments of the path
            connection: The connection used for this path.
        """
        super().__init__(*segments)
        self.connection = connection

    def with_segments(self, *segments):  # noqa: D102 (Built in)
        return type(self)(*segments, connection=self.connection)

    def rmdir(self) -> None:
        """Removes the given empty directory."""
        try:
            self.connection.run_process(["rmdir", str(self)])
        except exceptions.FailedProcessError as e:
            if "No such file or directory" not in e.stderr:
                raise

    def exists(self) -> bool:
        """
        Returns:
            True if the location exists.
        """
        try:
            result = self.connection.run_process(["ls", "-d", str(self)])
        except exceptions.FailedProcessError as e:
            if "No such file or directory" in e.stderr:
                return False

            raise

        return result.strip() != ""

    def mkdir(self, parents: bool = False) -> None:
        """
        Creates a directory.

        Args:
            parents: Also creates parent directories and doesn't fail if path exist.
        """
        self.connection.run_process(["mkdir", str(self)] + ["-p"] * parents)

    def rename(self, target: PurePath) -> None:
        """
        Renames/Moves the path to the target location.

        Args:
            target: The target location to move the object to.
        """
        self.connection.run_process(["mv", str(self), str(target)])

    def iterdir(self) -> list["BackupHostPath"]:
        """
        Returns:
            A list of Paths containing all items in the current directory.
        """
        result = sorted(self.connection.run_process(["ls", str(self)]).strip().split("\n"))

        if result == [""]:
            return []

        return [self / x for x in result]


@dataclass(frozen=True)
class Snapshot:
    """Describes a b4_snapshot."""

    name: str
    subvolumes: list[BackupHostPath]
    base_path: BackupHostPath

    _subvolume_delimiter: str = "!"

    @classmethod
    def from_new(
        cls, name: str, subvolumes: list[BackupHostPath], base_path: BackupHostPath
    ) -> "Snapshot":
        """
        Create instance from the backup target location.

        Args:
            name: Name of the snapshot
            subvolumes: List of subvolumes without delimiter translation
            base_path: Location of this snapshot
        """
        return Snapshot(
            name=name,
            subvolumes=[cls.escape_path(x) for x in subvolumes],
            base_path=base_path,
        )

    @classmethod
    def escape_path(cls, path: BackupHostPath) -> BackupHostPath:
        """
        Returns:
            Escaped variant of subvolume path.
        """
        return BackupHostPath(
            str(path).replace("/", cls._subvolume_delimiter),
            connection=path.connection,
        )

    @classmethod
    def unescape_path(cls, path: BackupHostPath) -> BackupHostPath:
        """
        Returns:
            Recreates a path from an escaped variant of subvolume path.
        """
        return BackupHostPath(
            str(path).replace(cls._subvolume_delimiter, "/"),
            connection=path.connection,
        )

    @property
    def subvolumes_unescaped(self) -> Generator[BackupHostPath, None, None]:
        """
        Returns:
            List all subvolumes without delimiter translation as relative paths.
        """
        return (
            self.unescape_path(
                BackupHostPath(
                    str(x).lstrip("!"),
                    connection=x.connection,
                )
            )
            for x in self.subvolumes
        )


@dataclass
class RetentionGroup:
    """
    Contains the retention ruleset for a target.

    Attributes:
        name: Name of the retention ruleset
        target_retention: The retention ruleset for the target itself
        is_source: True if this is a source retention ruleset
        obsolete_snapshots: All snapshots in this set will be condidered obsolete
    """

    name: str
    target_retention: dict[str, str]
    is_source: bool = True
    obsolete_snapshots: set[str] = field(default_factory=set)

    @classmethod
    def from_target(
        cls,
        retention_name: str,
        target: BackupTarget,
        is_source: bool = True,
        obsolete_snapshots: set[str] | None = None,
    ) -> "RetentionGroup":
        """
        Create an instance from a target and ruleset name.

        Args:
            retention_name: Name of the retention ruleset to select from the target
            target: Target to get the ruleset from
            is_source: Select source ruleset or destination ruleset
            obsolete_snapshots: All snapshots in this set will be condidered obsolete

        Returns:
            RetentionGroup instance
        """
        target_retentions = target.src_retention if is_source else target.dst_retention
        target_retention = target_retentions.get(retention_name) or target_retentions[DEFAULT]

        return RetentionGroup(
            name=retention_name,
            target_retention=target_retention,
            is_source=is_source,
            obsolete_snapshots=obsolete_snapshots or set(),
        )


@dataclass(frozen=True)
class ChoiceSelector:
    """
    Describes a set of data, with dynamic choices.

    Attributes:
        data: Contains the actual data
    """

    data: list[str] = field(default_factory=list)

    def resolve_target(self, targets: Iterable[str]) -> list[str]:
        """
        Resolves a target selector and returns a list based on the selection.

        Returns:
            List of resolved items
        """
        expanded_data: set[str] = set()
        for item in self.data:
            if item in targets:
                expanded_data.add(item)
                continue

            for target_name in targets:
                if PurePath(target_name).is_relative_to(item):
                    expanded_data.add(target_name)

        return list(expanded_data - {"_default"})

    def resolve_retention_name(self, snapshot_names: Iterable[str]) -> list[str]:
        """
        Resolves a retention_name selector and returns a list based on the selection.

        Returns:
            List of resolved items
        """
        if self.data == ["ALL"]:
            return list({x.split("_", maxsplit=1)[1] for x in snapshot_names})

        return self.data
