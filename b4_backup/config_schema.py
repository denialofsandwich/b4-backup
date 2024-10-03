"""
This module contains the config structure and it's default values.

The config is using the YAML syntax and this file describes the structure of it.
"""

import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePath
from typing import Any, Optional

import omegaconf
from omegaconf import II, MISSING

DEFAULT = "_default"


class TargetRestoreStrategy(str, Enum):
    """
    Specifies the restore procedure to be used.

    Attributes:
        SAFE: Just copy the snapshot back to the source snapshot directory without touching the target directory
        REPLACE: Bases safe, but also replace the target subvolumes with the copied one. Works by moving the original target away and then copy the snapshot to that place. Revertable by using the REPLACE snapshot name.
    """

    SAFE = "safe"
    REPLACE = "replace"


class SubvolumeBackupStrategy(str, Enum):
    """
    Backup strategy for subvolumes.

    Attributes:
        IGNORE: The subvolume will be ignored during the backup
        SOURCE_ONLY: The subvolume will be kept only on source and not sent to destination
        FULL: The subvolume will be sent to destination
    """

    IGNORE = "ignore"
    SOURCE_ONLY = "source_only"
    FULL = "full"


class SubvolumeFallbackStrategy(str, Enum):
    """
    Fallback strategy for subvolumes on a restore if the backup subvolume is already deleted.

    Attributes:
        DROP: The subvolume is lost after a restore (Use case: Docker artifacts or everywhere else where btrfs subvolumes are created dynamically)
        NEW: An empty subvolume is created at that place (Use case: Cache directories)
        KEEP: The old subvolume will be copied at the new place, if doesn't exist, a new one will be created (Use case: Steam library)
    """

    DROP = "drop"
    NEW = "new"
    KEEP = "keep"


class OnDestinationDirNotFound(str, Enum):
    """
    How to behave, if the destination directory does not exist.

    Attributes:
        CREATE: Create the missing directory structure and proceed without an error.
        FAIL: Throw an error and stop execution.
    """

    CREATE = "create"
    FAIL = "fail"


@dataclass
class TargetSubvolume:
    """
    Defines how to handle a specific subvolume in a target.

    Args:
        backup_strategy: How to handle the subvolume during backup
        fallback_strategy: How to handle the subvolume during restore if the backup subvolume is already deleted
    """

    backup_strategy: SubvolumeBackupStrategy = II(f"..{DEFAULT}.backup_strategy")
    fallback_strategy: SubvolumeFallbackStrategy = II(f"..{DEFAULT}.fallback_strategy")


@dataclass
class BackupTarget:
    """
    Defines a single backup target.

    Args:
        source: Path or URL you want to backup. Needs to be a btrfs subvolume
        destination: Path or URL where you want to send snapshots. If None, snapshots will only be on source side
        restore_strategy: Default procedure to restore a backup
        src_snapshot_dir: Directory where source snapshots relative to the mount point of the btrfs volume are located
        src_retention: Retention rules for snapshots located at the source
        dst_retention: Retention rules for snapshots located at the destination
        replaced_target_ttl: The minimum time the old replaced subvolume should be kept
        subvolume_rules: Contains rules for how to handle the subvolumes of a target
    """

    source: str
    destination: Optional[str] = II(f"..{DEFAULT}.destination")
    if_dst_dir_not_found: OnDestinationDirNotFound = II(f"..{DEFAULT}.if_dst_dir_not_found")
    restore_strategy: TargetRestoreStrategy = II(f"..{DEFAULT}.restore_strategy")
    src_snapshot_dir: Path = II(f"..{DEFAULT}.src_snapshot_dir")
    src_retention: dict[str, dict[str, str]] = field(default_factory=dict)
    dst_retention: dict[str, dict[str, str]] = field(default_factory=dict)
    replaced_target_ttl: str = II(f"..{DEFAULT}.replaced_target_ttl")
    subvolume_rules: dict[str, TargetSubvolume] = II(f"..{DEFAULT}.subvolume_rules")


@dataclass
class BaseConfig:
    """
    The root level of the configuration.

    Args:
        backup_targets: An object containing all targets to backup
        default_targets: List of default targets to use if not specified
        timezone: Timezone to use
        logging: Python logging configuration settings (logging.config.dictConfig).
    """

    backup_targets: dict[str, BackupTarget] = field(
        default_factory=lambda: {
            DEFAULT: BackupTarget(
                source=MISSING,
                destination=None,
                if_dst_dir_not_found=OnDestinationDirNotFound.CREATE,
                restore_strategy=TargetRestoreStrategy.SAFE,
                src_snapshot_dir=Path(".b4_backup"),
                src_retention={DEFAULT: {"all": "1"}},
                dst_retention={DEFAULT: {"all": "forever"}},
                replaced_target_ttl="24hours",
                subvolume_rules={
                    DEFAULT: TargetSubvolume(
                        backup_strategy=SubvolumeBackupStrategy.FULL,
                        fallback_strategy=SubvolumeFallbackStrategy.DROP,
                    ),
                    "/": TargetSubvolume(),
                },
            )
        }
    )

    default_targets: list[str] = field(default_factory=list)
    timezone: str = "utc"

    logging: dict[str, Any] = II(
        "oc.create:${from_file:" + str(Path(__file__).parent / "default_logging_config.yml") + "}"
    )

    # Internal only
    # May change at runtime
    config_path: Path = field(default=Path("~/.config/b4_backup.yml"))

    def __post_init__(self):
        """Used for validation of the values."""
        options = set(self.backup_targets) - {DEFAULT}
        for target in self.default_targets:
            if not any(PurePath(x).is_relative_to(target) for x in options):
                raise omegaconf.errors.ValidationError(
                    textwrap.dedent(
                        f"""\
                        Item '{target}' is not in 'backup_targets' but defined in 'default_targets'
                            full_key: default_targets
                            object_type={self.__class__.__name__}"""
                    )
                )
