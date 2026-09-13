import socket

import pytest

from tests.conftest import NetworkAccessBlockedError


def test_non_loopback_connection_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(NetworkAccessBlockedError),
    ):
        sock.connect(("203.0.113.1", 443))  # TEST-NET-3, never routed


def test_loopback_connection_is_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())
