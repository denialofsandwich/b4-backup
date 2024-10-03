from pathlib import Path
from typing import Type
from unittest.mock import MagicMock, call

import paramiko
import pytest

from b4_backup import exceptions
from b4_backup.main import connection


@pytest.mark.parametrize(
    ("test_input", "expect"),
    [
        (
            "ssh://root:1234@main.example.com:22/",
            connection.URL(
                protocol="ssh",
                user="root",
                password="1234",
                host="main.example.com",
                port=22,
                location=Path("/"),
            ),
        ),
        (
            "ssh://root:1234@main.example.com:22/opt/backup",
            connection.URL(
                protocol="ssh",
                user="root",
                password="1234",
                host="main.example.com",
                port=22,
                location=Path("/opt/backup"),
            ),
        ),
        (
            "/opt/test",
            connection.URL(
                protocol=None,
                user="root",
                password=None,
                host=None,
                port=0,
                location=Path("/opt/test"),
            ),
        ),
        (
            "backup/test",
            connection.URL(
                protocol=None,
                user="root",
                password=None,
                host=None,
                port=0,
                location=Path("backup/test"),
            ),
        ),
        (
            "ssh://root@main.example.com:990/b",
            connection.URL(
                protocol="ssh",
                user="root",
                password=None,
                host="main.example.com",
                port=990,
                location=Path("/b"),
            ),
        ),
        (
            "ssh://main.example.com/b",
            connection.URL(
                protocol="ssh",
                user="root",
                password=None,
                host="main.example.com",
                port=22,
                location=Path("/b"),
            ),
        ),
    ],
)
def test_url_from_url(test_input, expect):
    # Act
    result = connection.URL.from_url(test_input)

    # Assert
    print(result)
    assert result == expect


@pytest.mark.parametrize(
    "test_input",
    ["root@test", "lxd:///hi", "example.com:22", ""],
)
def test_url_from_url__invalid_url(test_input):
    # Act / Assert
    with pytest.raises(exceptions.InvalidConnectionUrlError):
        connection.URL.from_url(test_input)


@pytest.mark.parametrize(
    ("test_input", "expected_type"),
    [
        ("/opt/backups", connection.LocalConnection),
        ("ssh://main.example.com/b", connection.SSHConnection),
    ],
)
def test_connection_from_url(test_input: str, expected_type: Type):
    # Act
    result = connection.Connection.from_url(test_input)

    # Assert
    assert isinstance(result, expected_type)


def test_connection_from_url__unknown_protocol():
    # Act / Assert
    with pytest.raises(exceptions.UnknownProtocolError):
        connection.Connection.from_url("http://example.com/test")


def test_open_ssh_connection(monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(paramiko, "SSHClient", MagicMock())

    # Act
    with connection.SSHConnection(host="example.com", location=Path("/test")) as _con:
        ...

    # Assert
    assert isinstance(paramiko.SSHClient, MagicMock)
    paramiko.SSHClient: MagicMock  # type: ignore  # noqa: B032

    assert paramiko.SSHClient.called is True

    fake_ssh = paramiko.SSHClient()
    assert fake_ssh.connect.call_args == call(
        "example.com",
        username="root",
        password=None,
        port=22,
    )


@pytest.mark.parametrize(
    "connection_url",
    [
        "/tmp/dummy",
        "ssh://example.com/tmp/dummy",
    ],
)
def test_run_process_success(connection_url: str, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(paramiko, "SSHClient", MagicMock())
    assert isinstance(paramiko.SSHClient, MagicMock)
    paramiko.SSHClient: MagicMock  # type: ignore  # noqa: B032
    fake_ssh = paramiko.SSHClient()
    fake_ssh.exec_command = MagicMock(
        return_value=(
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
    )
    fake_ssh.exec_command()[1].read().decode = MagicMock(return_value="snickers\n")
    fake_ssh.exec_command()[1].channel.recv_exit_status = MagicMock(return_value=0)

    connection_instance = connection.Connection.from_url(connection_url)

    # Act
    with connection_instance as con:
        result = con.run_process(["echo", "snickers"])

    # Assert
    assert paramiko.SSHClient.called is True

    print(result)
    assert result == "snickers\n"


@pytest.mark.parametrize(
    "connection_url",
    [
        "/tmp/dummy",  # Local
        "ssh://example.com/tmp/dummy",  # SSH
    ],
)
def test_run_process_error(connection_url, monkeypatch: pytest.MonkeyPatch):
    # Arrange
    monkeypatch.setattr(paramiko, "SSHClient", MagicMock())
    assert isinstance(paramiko.SSHClient, MagicMock)
    paramiko.SSHClient: MagicMock  # type: ignore  # noqa: B032
    fake_ssh = paramiko.SSHClient()
    fake_ssh.exec_command = MagicMock(
        return_value=(
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
    )
    fake_ssh.exec_command()[1].read().decode = MagicMock(return_value="")
    fake_ssh.exec_command()[1].channel.exit_status = 1

    connection_instance = connection.Connection.from_url(connection_url)

    # Act
    with (
        connection_instance as con,
        pytest.raises(exceptions.FailedProcessError) as exc_info,
    ):
        _result = con.run_process(["false"])

    assert all(
        x in exc_info.value.args[0] for x in ["exited with a non-zero error", "STDOUT", "STDERR"]
    )


@pytest.mark.parametrize(
    ("con", "expected_result"),
    [
        (
            connection.SSHConnection(host="example.com", location=Path("/")),
            "ssh -p 22 root@example.com ",
        ),
        (connection.LocalConnection(Path("/")), ""),
    ],
)
def test_build_command(con: connection.Connection, expected_result: str):
    # Act
    result = con.exec_prefix

    # Assert
    assert result == expected_result
