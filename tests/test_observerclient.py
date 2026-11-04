"""Unit tests for ObserverClient."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from tp_final_integrador_is2.observerclient import (
    ObserverClient,
    build_argument_parser,
    main,
    normalize_argv,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_normalize_argv_replaces_typographic_dashes() -> None:
    """Verify normalize_argv converts en-dash and em-dash to hyphen."""
    raw = ["\u2013s=host.domain", "\u2014p=9090", "\u2013v", "-o=out.json"]
    normalized = normalize_argv(raw)
    assert normalized == ["-s=host.domain", "-p=9090", "-v", "-o=out.json"]


def test_build_argument_parser_defaults_and_custom() -> None:
    """Verify argument parser extracts defaults and custom flags."""
    parser = build_argument_parser()
    defaults = parser.parse_args([])
    assert defaults.server == "localhost"
    assert defaults.port == 8080
    assert defaults.output_file is None
    assert defaults.verbose is False
    assert defaults.retry_interval == 30.0

    custom = parser.parse_args(
        ["-s", "remote.srv", "-p", "8888", "-o", "log.json", "-v", "-r", "5.0"],
    )
    assert custom.server == "remote.srv"
    assert custom.port == 8888
    assert custom.output_file == "log.json"
    assert custom.verbose is True
    assert custom.retry_interval == 5.0


def test_build_subscription_payload() -> None:
    """Verify subscription payload contains CPU UUID and subscribe action."""
    client = ObserverClient()
    payload = client.build_subscription_payload()
    assert payload["ACTION"] == "subscribe"
    assert payload["UUID"]
    assert payload["UUID"] != "XXXXXXXXXXXXXXXXXXXXXXX"


def test_handle_notification_stdout_and_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify handle_notification writes to stdout and to file."""
    client = ObserverClient()
    msg = {"id": "UADER-FCyT-IS2", "status": "updated"}
    out_file = tmp_path / "subfolder" / "notif.json"

    client.handle_notification(msg, out_file)
    captured = capsys.readouterr()
    assert '"status": "updated"' in captured.out
    assert out_file.is_file()
    assert json.loads(out_file.read_text(encoding="utf-8")) == msg

    # Also verify non-dict string notification
    client.handle_notification("Plain string notification", None)
    captured2 = capsys.readouterr()
    assert "Plain string notification" in captured2.out


def test_connect_and_listen_receives_notifications() -> None:
    """Verify connect_and_listen receives and parses streamed JSON messages."""
    client = ObserverClient(host="127.0.0.1", port=8080)
    mock_socket = MagicMock()
    # Simulate receiving two consecutive notifications over the TCP stream
    msg1 = json.dumps({"event": 1}) + "\n"
    msg2 = json.dumps({"event": 2}) + "\n"
    mock_socket.recv.side_effect = [
        msg1.encode("utf-8"),
        msg2.encode("utf-8"),
    ]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        received = client.connect_and_listen(max_messages=2)
        assert received == 2
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 8080))
        # Ensure subscription payload was sent
        sent_data = mock_socket.sendall.call_args[0][0].decode("utf-8")
        assert '"ACTION": "subscribe"' in sent_data


def test_connect_and_listen_server_closes_connection() -> None:
    """Verify connect_and_listen raises ConnectionError when server closes socket."""
    client = ObserverClient()
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b""]  # EOF

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        with pytest.raises(ConnectionError, match="finalizada por el servidor"):
            client.connect_and_listen()


def test_connect_and_listen_handles_timeout_and_continues() -> None:
    """Verify connect_and_listen handles timeout and continues loop."""
    client = ObserverClient()
    mock_socket = MagicMock()
    # First recv raises TimeoutError, second returns a message
    msg = json.dumps({"update": True})
    mock_socket.recv.side_effect = [
        TimeoutError("timed out"),
        msg.encode("utf-8"),
    ]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        count = client.connect_and_listen(max_messages=1)
        assert count == 1


def test_stop_signals_stop_event() -> None:
    """Verify stop signals event and closes socket cleanly."""
    client = ObserverClient()
    assert client.is_stopped is False
    client.stop()
    assert client.is_stopped is True


def test_run_reconnect_loop_with_limit() -> None:
    """Verify run re-attempts connection upon failure until limit."""
    client = ObserverClient(retry_interval=0.01)
    with patch.object(
        client,
        "connect_and_listen",
        side_effect=ConnectionError("Failed connection"),
    ) as mock_listen:
        client.run(max_reconnects=3)
        assert mock_listen.call_count == 3


def test_run_stops_on_max_messages() -> None:
    """Verify run terminates after reaching target total messages."""
    client = ObserverClient()
    with patch.object(client, "connect_and_listen", return_value=5) as mock_listen:
        client.run(max_messages=5)
        assert mock_listen.call_count == 1


def test_run_propagates_unexpected_exception() -> None:
    """Verify non-connection errors are re-raised."""
    client = ObserverClient()
    with (
        patch.object(
            client,
            "connect_and_listen",
            side_effect=RuntimeError("Fatal error"),
        ),
        pytest.raises(RuntimeError, match="Fatal error"),
    ):
        client.run()


def test_main_cli_keyboard_interrupt() -> None:
    """Verify main returns 0 on KeyboardInterrupt."""
    with patch.object(ObserverClient, "run", side_effect=KeyboardInterrupt):
        code = main([])
        assert code == 0


def test_main_cli_unexpected_error() -> None:
    """Verify main returns 1 on unexpected exception."""
    with patch.object(ObserverClient, "run", side_effect=ValueError("Invalid config")):
        code = main(["-v"])
        assert code == 1


def test_main_cli_normal_exit() -> None:
    """Verify main returns 0 on clean completion."""
    with patch.object(ObserverClient, "run", return_value=None):
        code = main(["-s", "localhost", "-p", "8080"])
        assert code == 0
