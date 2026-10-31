"""Restarting Countersign straight after a run must work; a real port clash must still be reported."""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from bench.run import free_port
from countersign.gateway_runner import ensure_ports_free


def test_a_port_another_process_listens_on_is_reported():
    with socket.create_server(("127.0.0.1", 0)) as listener:
        taken = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match=str(taken)):
            ensure_ports_free(SimpleNamespace(gateway_mcp_port=taken, gateway_api_port=free_port()))


def test_a_port_with_only_closed_connections_left_is_free():
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port))
        accepted, _ = listener.accept()
        accepted.close()  # The server closing first leaves the port in TIME_WAIT, as a stopped gateway does.
        client.close()
    ensure_ports_free(SimpleNamespace(gateway_mcp_port=port, gateway_api_port=free_port()))
