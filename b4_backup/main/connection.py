import logging
import re
import shlex
import subprocess
from abc import ABCMeta, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import PurePath

import paramiko

from b4_backup import exceptions

log = logging.getLogger("b4_backup.connection")


@dataclass
class URL:
    """
    Contains an URL.

    Args:
        protocol: protocol used. eg. ssh
        user: Username
        password: Password
        host: Hostname
        port: Port
        location: Protocol specific location
    """

    protocol: str | None = None
    user: str = "root"
    password: str | None = None
    host: str | None = None
    port: int = 0
    location: PurePath = PurePath("/")

    _url_pattern = re.compile(
        r"^(?:(?P<protocol>[a-zA-Z0-9_\-]+):\/\/)(?:(?P<user>[a-zA-Z0-9_\-]+)(?::(?P<password>[a-zA-Z0-9_\-]+))?@)?(?P<host>[a-zA-Z0-9_.\-]+)(?::(?P<port>[0-9]+))?(?P<location>\/[\/a-zA-Z0-9_.\-]*)?$"
    )
    _local_dir_pattern = re.compile(r"^(?P<location>[\/a-zA-Z0-9_.\-]+)$")
    _protocol_mapping = {"ssh": 22, None: 0}

    @classmethod
    def from_url(cls, source: str) -> "URL":
        """
        Create an instance by providing an URL string.

        Args:
            source: URL string

        Returns:
            ParsedURL instance
        """
        result = cls._url_pattern.match(source)

        if not result:
            result = cls._local_dir_pattern.match(source)

        if not result:
            raise exceptions.InvalidConnectionUrlError(
                f"The connection url {source} got an invalid format."
            )

        result_dict = asdict(URL())
        result_dict.update(result.groupdict())

        if result_dict["protocol"] is not None:
            result_dict["protocol"] = result_dict["protocol"].lower()

        return URL(
            protocol=result_dict["protocol"],
            user=result_dict["user"] or URL.user,
            password=result_dict["password"],
            host=result_dict["host"],
            port=int(result_dict["port"] or cls._protocol_mapping.get(result_dict["protocol"], 0)),
            location=PurePath(result_dict["location"] or "/"),
        )


class Connection(metaclass=ABCMeta):
    """An abstract connection wrapper to execute commands on machines."""

    def __init__(self, location: PurePath) -> None:
        """
        Args:
            location: Target directory or file.
        """
        self.location = location

        self.connected: bool = False

    @classmethod
    def from_url(cls, url: str) -> "Connection":
        """
        Parse the URL and return a fitting connection instance.

        Args:
            url: URL string to parse

        Returns:
            Connection instance
        """
        parsed_url = URL.from_url(url)

        if parsed_url.protocol is None:
            return LocalConnection(parsed_url.location)

        if parsed_url.protocol == "ssh":
            assert parsed_url.host is not None

            return SSHConnection(
                host=parsed_url.host,
                port=parsed_url.port,
                user=parsed_url.user,
                password=parsed_url.password,
                location=parsed_url.location,
            )

        raise exceptions.UnknownProtocolError

    @abstractmethod
    def run_process(self, command: list[str]) -> str:
        """
        Run a process without interaction and return the result.

        Args:
            command: List of parameters
        Returns:
            stdout of process.
        """

    @abstractmethod
    def open(self) -> "Connection":
        """
        Open the connection to the target host.

        Returns:
            Itself
        """

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""

    @property
    @abstractmethod
    def exec_prefix(self) -> str:
        """
        Returns:
            Prefix to run commands on the target using local commands.
        """

    def __enter__(self) -> "Connection":
        """Entrypoint in a "with" statement."""
        return self.open()

    def __exit__(self, *args, **kwargs) -> None:
        """Endpoint in a "with" statement."""
        self.close()


class LocalConnection(Connection):
    """A connection wrapper to execute commands on the local machine."""

    def __init__(self, location: PurePath) -> None:
        """
        Args:
            location: Target directory or file.
        """
        super().__init__(location)

        self.location: PurePath = location

    def run_process(self, command: list[str]) -> str:
        """
        Run a process without interaction and return the result.

        Args:
            command: List of parameters
        Returns:
            stdout of process.
        """
        log.debug("Start local process:\n%s", command)
        with subprocess.Popen(  # noqa: S603
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        ) as process:
            stdout, stderr = process.communicate()
            stdout = stdout.decode()
            stderr = stderr.decode()

        if process.returncode:
            raise exceptions.FailedProcessError(command, stdout, stderr)

        return stdout

    def open(self) -> "Connection":
        """
        Open the connection to the target host.

        Returns:
            Itself
        """
        self.connected = True

        return self

    def close(self) -> None:
        """Close the connection."""
        assert self.connected, "Connection already closed"

        self.connected = False

    @property
    def exec_prefix(self) -> str:
        """
        Returns:
            Prefix to run commands on the target using local commands.
        """
        return ""


class SSHConnection(Connection):
    """A connection wrapper to execute commands on remote machines via SSH."""

    def __init__(
        self,
        host: str,
        location: PurePath,
        port: int = 22,
        user: str = "root",
        password: str | None = None,
    ) -> None:
        """
        Args:
            host: Hostname
            location: Target directory or file
            port: Port
            user: Username
            password: Optional password. SSH key recommended.
        """
        super().__init__(location)

        self.host = host
        self.port = port
        self.user = user
        self.password = password

        self._ssh_client: paramiko.SSHClient = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def run_process(self, command: list[str]) -> str:
        """
        Run a process without interaction and return the result.

        Args:
            command: List of parameters
        Returns:
            stdout of process.
        """
        log.debug("Start SSH process:\n%s", command)

        _stdin, stdout, stderr = self._ssh_client.exec_command(shlex.join(command))
        stdout_str = stdout.read().decode()
        stderr_str = stderr.read().decode()

        if stdout.channel.recv_exit_status():
            raise exceptions.FailedProcessError(command, stdout_str, stderr_str)

        return stdout_str

    def open(self) -> "SSHConnection":
        """
        Open the connection to the target host.

        Returns:
            Itself
        """
        self._ssh_client.connect(
            self.host,
            username=self.user,
            password=self.password,
            port=self.port,
        )
        self.connected = True

        return self

    def close(self) -> None:
        """Close the connection."""
        assert self.connected, "Connection already closed"

        self._ssh_client.close()
        self.connected = False

    @property
    def exec_prefix(self) -> str:
        """
        Returns:
            Prefix to run commands on the target using local commands.
        """
        return f"ssh -p {self.port} {self.user}@{self.host} "
