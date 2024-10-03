"""Contains all custom exceptions used in this program."""


class BaseBtrfsBackupError(Exception):
    """Base of all custom exceptions."""


class FailedProcessError(BaseBtrfsBackupError):
    """Raised, if a process returns a non-zero return code."""

    def __init__(self, cmd: list[str], stdout: str = "", stderr: str = ""):
        """
        Args:
            cmd: failed command.
            stdout: standard output of that process.
            stderr: standard error of that process.
        """
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr

        super().__init__(
            "The following process exited with a non-zero error:\n"
            f"===  CMD   ===\n{' '.join(cmd)}\n============\n"
            f"=== STDOUT ===\n{stdout}============\n"
            f"=== STDERR ===\n{stderr}============\n"
        )


class InvalidConnectionUrlError(BaseBtrfsBackupError):
    """Raised, if the connection url is malformed."""


class UnknownProtocolError(InvalidConnectionUrlError):
    """Raised, if an unsupported protocol is used."""


class InvalidRetentionRuleError(BaseBtrfsBackupError):
    """Raised, if the retention rule string is malformed."""


class BtrfsSubvolumeNotFoundError(BaseBtrfsBackupError):
    """Raised, if a BTRFS subvolume does not exist."""


class SnapshotNotFoundError(BaseBtrfsBackupError):
    """Raised, if a BTRFS backup snapshot does not exist."""


class DestinationDirectoryNotFoundError(BaseBtrfsBackupError):
    """Raised, if the destination is not found and configured to fail."""


class BtrfsPartitionNotFoundError(BaseBtrfsBackupError):
    """Raised, if the target location is not a valid btrfs partition."""
