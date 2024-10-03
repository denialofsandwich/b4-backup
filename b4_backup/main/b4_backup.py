import logging
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Iterable

import arrow

from b4_backup import exceptions
from b4_backup.config_schema import (
    BaseConfig,
    SubvolumeFallbackStrategy,
    TargetRestoreStrategy,
)
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

log = logging.getLogger("b4_backup.main")


@dataclass
class B4Backup:
    """
    Main controller class for the backups. Does the backups and stuff.

    Args:
        timezone: Timezone to use
    """

    timezone: str = BaseConfig.timezone

    _size_pattern = re.compile(r"^(?:([0-9]+)(second|minute|hour|day|week|month|year)?s?)$")
    _timestamp_fmt = "YYYY-MM-DD-HH-mm-ss"

    def backup(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None,
        snapshot_name: str,
    ) -> None:
        """
        Performs a backup for a single target.

        dst_host can be none. In this case nothing will be sent and only a snapshot + clean up on source side is performed.

        Args:
            src_host: An active source host instance
            dst_host: An active destination host instance
            snapshot_name: The name of the new snapshot
        """
        log.info("Snapshot name: %s", snapshot_name)

        src_host.create_snapshot(snapshot_name)

        if dst_host:
            src_host.send_snapshot(dst_host, snapshot_name)

        retention_name = ChoiceSelector([self._extract_retention_name(snapshot_name)])
        self.clean(
            src_host=src_host,
            dst_host=dst_host,
            retention_names=retention_name,
        )

    def restore(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None,
        snapshot_name: str,
        strategy: TargetRestoreStrategy,
    ) -> None:
        """
        Restore a snapshot to one or more targets.

        Args:
            src_host: An active source host instance
            dst_host: An active destination host instance
            snapshot_name: Name of the snapshot you want to restore
            strategy: Restore strategy or procedure to apply
        """
        if snapshot_name == "REPLACE":
            if strategy != TargetRestoreStrategy.REPLACE:
                raise exceptions.SnapshotNotFoundError(
                    "REPLACE can only be restored using REPLACE restore strategy"
                )

            log.info("Reverting last REPLACE restore")
            self._rollback_replace(src_host)

        elif strategy == TargetRestoreStrategy.REPLACE:
            log.info("Using REPLACE restore strategy")
            self._restore_replace(src_host, dst_host, snapshot_name)

        else:
            log.info("Using SAFE restore strategy")
            self._restore_safe(src_host, dst_host, snapshot_name)

    def sync(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost,
    ) -> None:
        """
        Send unsended snapshots to the destination and clean them.

        Args:
            src_host: An active source host instance
            dst_host: An active destination host instance
        """
        self.clean(src_host, dst_host)

        src_snapshots = src_host.snapshots()
        dst_snapshots = dst_host.snapshots()

        for snapshot_name in src_snapshots.keys() - dst_snapshots.keys():
            src_host.send_snapshot(dst_host, snapshot_name)

        self.clean(src_host, dst_host)

    def clean(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None = None,
        retention_names: ChoiceSelector = ChoiceSelector(["ALL"]),
    ) -> None:
        """
        Apply a retention ruleset on the selected targets.

        Args:
            src_host: An active source host instance
            dst_host: An active destination host instance
            retention_names: Name suffix of this backup (retention ruleset)
        """
        self._clean_target(src_host, dst_host, retention_names)
        self._clean_replace(src_host)

    def delete(
        self,
        host: BackupTargetHost,
        snapshot_name: str,
    ) -> None:
        """
        Delete a specific snapshot from a specific target/host.

        Args:
            host: the selected target host
            snapshot_name: The name of the snapshot to delete
        """
        snapshots = host.snapshots()

        if snapshot_name not in snapshots:
            log.warning("Snapshot %s does not exist on %s", snapshot_name, host.type)
            return

        host.delete_snapshot(snapshots[snapshot_name])

    def delete_all(
        self,
        host: BackupTargetHost,
        retention_names: ChoiceSelector = ChoiceSelector(["ALL"]),
    ) -> None:
        """
        Delete all snapshots from a specific target/host/retention item.

        Args:
            host: the selected target host
            retention_names: The retention names the snapshots have to contain
        """
        resolved_retention_names = set(retention_names.resolve_retention_name(host.snapshots()))

        for snapshot_name, snapshot in host.snapshots().items():
            if self._extract_retention_name(snapshot_name) not in resolved_retention_names:
                continue

            host.delete_snapshot(snapshot)

    def _restore_replace(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None,
        snapshot_name: str,
    ) -> None:
        self._restore_safe(src_host, dst_host, snapshot_name)
        replace_path = self._remove_target(src_host)

        snapshot = src_host.snapshots()[snapshot_name]
        self._restore_snapshot(src_host, snapshot, existing_replaced_target=replace_path)

        self._clean_replace(src_host)

    def _restore_safe(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None,
        snapshot_name: str,
    ) -> None:
        if dst_host:
            dst_host.send_snapshot(src_host, snapshot_name)
            return

        log.warning("Running in offline mode. Destination host snapshots are unavailable.")

        if snapshot_name not in src_host.snapshots():
            raise exceptions.SnapshotNotFoundError(snapshot_name)

    def _rollback_replace(self, host: SourceBackupTargetHost) -> None:
        replaced_targets_dir = (
            host.mount_point() / host.target_config.src_snapshot_dir / "replace" / host.name
        )

        replaced_targets_dir.mkdir(parents=True)
        replaced_targets = replaced_targets_dir.iterdir()

        if not replaced_targets:
            raise exceptions.SnapshotNotFoundError("No old replace available to rollback")

        self._remove_target(host)

        replaced_targets[-1].rename(host.path())  # move

        self._clean_replace(host)

    def _remove_target(self, host: SourceBackupTargetHost) -> BackupHostPath | None:
        if not host.path().exists():
            return None

        replace_name = self.generate_snapshot_name()
        log.info("Replace name: %s", replace_name)

        replace_dir = (
            host.mount_point()
            / host.target_config.src_snapshot_dir
            / "replace"
            / host.name
            / replace_name
        )

        replace_dir.parent.mkdir(parents=True)
        host.path().rename(replace_dir)

        return replace_dir

    def generate_snapshot_name(self, name: str | None = None) -> str:
        """
        Generate a name for a new snapshot.

        Args:
            name: Retention rule name

        Returns:
            Name for a snapshot
        """
        snapshot_name = arrow.utcnow().to(self.timezone).format(self._timestamp_fmt)

        if name:
            snapshot_name += f"_{name}"

        return snapshot_name

    def _restore_snapshot(
        self,
        host: SourceBackupTargetHost,
        snapshot: Snapshot,
        existing_replaced_target: BackupHostPath | None = None,
    ) -> None:
        con = host.connection
        host.path(con.location.parent).mkdir(parents=True)

        for snapshot_subvol, subvolume_subvol_norm in zip(
            snapshot.subvolumes, snapshot.subvolumes_unescaped
        ):
            target_subvolume = host.path(con.location / subvolume_subvol_norm)
            target_subvolume.rmdir()

            target_subvolume.parent.mkdir(parents=True)
            con.run_process(
                [
                    "btrfs",
                    "subvolume",
                    "snapshot",
                    str(snapshot.base_path / snapshot.name / snapshot_subvol),
                    str(target_subvolume),
                ]
            )

        for subvolume_str in host.target_config.subvolume_rules:
            subvolume_path = PurePath(subvolume_str)
            if not subvolume_path.is_absolute():
                if (
                    host.target_config.subvolume_rules[subvolume_str].fallback_strategy
                    != SubvolumeFallbackStrategy.DROP
                ):
                    log.warning(
                        'Can\'t recreate subvolumes from relative subvolume_rule path "%s". Skipped. Use an absolute Path.',
                        subvolume_str,
                    )

                continue

            self._create_fallback_subvolume(host, subvolume_path, existing_replaced_target)

    def _create_fallback_subvolume(
        self,
        host: SourceBackupTargetHost,
        subvolume_path: PurePath,
        existing_replaced_target: BackupHostPath | None = None,
    ) -> None:
        subvolume_str = str(subvolume_path)
        rules = host.target_config.subvolume_rules[subvolume_str]

        target_subvolume_path = host.path() / PurePath(subvolume_str[1:])

        if target_subvolume_path.exists():
            log.debug("%s already exist", target_subvolume_path)
            return

        rt_subvolume: BackupHostPath | None = None
        if existing_replaced_target:
            rt_subvolume = existing_replaced_target / PurePath(subvolume_str[1:])

            if not rt_subvolume.exists():
                rt_subvolume = None

        target_subvolume_path.parent.mkdir(parents=True)

        if rules.fallback_strategy == SubvolumeFallbackStrategy.KEEP and rt_subvolume:
            rt_subvolume.rename(target_subvolume_path)

        elif rules.fallback_strategy == SubvolumeFallbackStrategy.NEW or (
            rules.fallback_strategy == SubvolumeFallbackStrategy.KEEP and not rt_subvolume
        ):
            host.connection.run_process(
                ["btrfs", "subvolume", "create", str(target_subvolume_path)]
            )

    def _clean_target(
        self,
        src_host: SourceBackupTargetHost,
        dst_host: DestinationBackupTargetHost | None,
        retention_names: ChoiceSelector,
    ) -> None:
        src_retentions: list[RetentionGroup] = []
        src_dst_retentions: list[RetentionGroup] = []
        dst_retentions: list[RetentionGroup] = []
        for retention_name in retention_names.resolve_retention_name(src_host.snapshots()):
            src_retentions.append(
                RetentionGroup.from_target(
                    retention_name=retention_name,
                    target=src_host.target_config,
                    is_source=True,
                )
            )
            # We want to make sure that unsended snapshots (from an offline backup) are not deleted
            # They can only be deleted, if the dst_retention is flagging the snapshot as obsolete, too
            src_dst_retentions.append(
                RetentionGroup.from_target(
                    retention_name=retention_name,
                    target=src_host.target_config,
                    is_source=False,
                )
            )

        if dst_host:
            for retention_name in retention_names.resolve_retention_name(dst_host.snapshots()):
                dst_retentions.append(
                    RetentionGroup.from_target(
                        retention_name=retention_name,
                        target=dst_host.target_config,
                        is_source=False,
                    )
                )
            self._apply_retention(dst_host, dst_retentions)

            # Already sended snapshots however can be deleted, if they are not retained through the src_retention
            dst_snapshots = set(dst_host.snapshots())
            for retention in src_dst_retentions:
                retention.obsolete_snapshots = dst_snapshots

        self._apply_retention(src_host, src_retentions + src_dst_retentions)

    def _apply_retention(
        self,
        host: BackupTargetHost,
        retentions: Iterable[RetentionGroup],
    ) -> None:

        # We only want to clean the selected retention_names
        snapshots = self._filter_snapshots(host.snapshots(), [x.name for x in retentions])

        retained_destination_snapshots: set[str] = set()
        retained_source_snapshots: set[str] = set()
        for retention in retentions:
            if retention.is_source:
                retained_source_snapshots |= self._retained_snapshots(
                    snapshots,
                    retention.target_retention,
                    retention.name,
                    retention.obsolete_snapshots,
                )
            else:
                retained_destination_snapshots |= self._retained_snapshots(
                    snapshots,
                    retention.target_retention,
                    retention.name,
                    retention.obsolete_snapshots,
                )

        for snapshot_name in sorted(
            snapshots.keys() - (retained_source_snapshots | retained_destination_snapshots)
        ):
            host.delete_snapshot(snapshots[snapshot_name])

        for snapshot_name in sorted(retained_destination_snapshots - retained_source_snapshots):
            host.delete_snapshot(
                snapshots[snapshot_name],
                subvolumes=list(host.source_subvolumes_from_snapshot(snapshots[snapshot_name])),
            )

    def _filter_snapshots(
        self, snapshots: dict[str, Snapshot], retention_names: Iterable[str]
    ) -> dict[str, Snapshot]:
        return {
            k: v for k, v in snapshots.items() if self._extract_retention_name(k) in retention_names
        }

    def _extract_retention_name(self, snapshot_name: str) -> str:
        return snapshot_name.split("_", maxsplit=1)[1]

    def _clean_replace(self, host: SourceBackupTargetHost) -> None:
        replaced_targets_dir = (
            host.mount_point() / host.target_config.src_snapshot_dir / "replace" / host.name
        )

        replaced_targets_dir.mkdir(parents=True)
        replaced_targets = sorted(replaced_targets_dir.iterdir(), reverse=True)

        if not replaced_targets:
            return

        for i, replaced_target in enumerate(replaced_targets):
            # I'm doing an off-label use of this function here
            # to test if the replace is obsolete
            if i == 0 and self._retained_snapshots(
                [replaced_target.name], {"all": host.target_config.replaced_target_ttl}
            ):
                continue

            self._remove_replaced_targets(host, replaced_target)

    def _remove_replaced_targets(
        self, host: SourceBackupTargetHost, replaced_target: PurePath
    ) -> None:
        target_subvolumes = [x for x in host.subvolumes() if x.is_relative_to(replaced_target)]

        for subvolume in reversed(target_subvolumes):
            host.connection.run_process(["btrfs", "subvolume", "delete", str(subvolume)])

    def _transpose_snapshot_subvolumes(
        self, snapshots: dict[str, Snapshot]
    ) -> dict[BackupHostPath, set[str]]:
        return_dict: dict[BackupHostPath, set[str]] = {}
        for snapshot_name, snapshot in snapshots.items():
            for subvolume in snapshot.subvolumes:
                if subvolume not in return_dict:
                    return_dict[subvolume] = set()

                return_dict[subvolume].add(snapshot_name)

        return return_dict

    def _retained_snapshots(
        self,
        snapshot_names: Iterable[str],
        retention: dict[str, str],
        retention_name: str | None = None,
        ignored_snapshots: set[str] | None = None,
    ) -> set[str]:
        ignored_snapshots = ignored_snapshots or set()

        snapshot_dates = [
            arrow.get(x.split("_")[0], self._timestamp_fmt)
            for x in snapshot_names
            if x not in ignored_snapshots
            and (not retention_name or x.split("_", maxsplit=1)[1] == retention_name)
        ]

        remaining_backups: set[arrow.Arrow] = set()
        for interval, duration in retention.items():
            remaining_backups.update(self._apply_retention_rule(interval, duration, snapshot_dates))

        return {
            x.format(self._timestamp_fmt) + f"_{retention_name}" * (retention_name is not None)
            for x in remaining_backups
        }

    def _apply_retention_rule(
        self, interval_str: str, duration_str: str, dates: list[arrow.Arrow]
    ) -> list[arrow.Arrow]:
        interval_size, interval_magnitude = self._timebox_str_extract(
            interval_str, is_interval=True
        )
        duration_size, duration_magnitude = self._timebox_str_extract(
            duration_str, is_interval=False
        )

        remaining: list[arrow.Arrow] = []
        for date in sorted(dates, reverse=True):
            if duration_magnitude != "forever" and (
                (
                    duration_magnitude is not None
                    and date
                    < arrow.utcnow().to(self.timezone).shift(**{duration_magnitude: -duration_size})
                )
                or (duration_magnitude is None and len(remaining) >= duration_size)
            ):
                break

            if not remaining:
                remaining.append(date)
                continue

            if interval_magnitude == "all":
                remaining.append(date)
            else:
                assert interval_magnitude is not None

                min_box, max_box = (
                    remaining[-1]
                    .shift(**{interval_magnitude: 1 - interval_size})
                    .span(interval_magnitude, count=interval_size)  # type: ignore
                )
                if date < min_box or date >= max_box:
                    remaining.append(date)

        return remaining

    def _timebox_str_extract(
        self, timebox_str: str, is_interval: bool = False
    ) -> tuple[int, str | None]:

        if is_interval and timebox_str == "all":
            return 0, "all"

        if not is_interval and timebox_str == "forever":
            return 0, "forever"

        size_pattern = self._size_pattern.match(timebox_str)
        if not size_pattern:
            raise exceptions.InvalidRetentionRuleError(
                f"Size pattern ({timebox_str}, interval:{is_interval}) is invalid"
            )

        size = size_pattern.group(1) or 0
        magnitude = size_pattern.group(2)

        if magnitude is not None:
            magnitude += "s"

        return int(size), magnitude
