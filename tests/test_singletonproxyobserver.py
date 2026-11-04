"""Unit and acceptance tests for SingletonProxyObserverServer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tp_final_integrador_is2.database import (
    CorporateDataRepository,
    CorporateLogRepository,
)
from tp_final_integrador_is2.proxy import CorporateDataProxy
from tp_final_integrador_is2.singletonproxyobserver import (
    SingletonProxyObserverServer,
    _parse_json_payload,
    build_argument_parser,
    main,
    normalize_argv,
)


def _make_mock_client_socket(chunks: list[bytes]) -> MagicMock:
    """Crea un socket simulado que provee fragmentos en recv y captura sendall."""
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [*chunks, b""]
    sent_buffers: list[bytes] = []

    def capture_sendall(data: bytes) -> None:
        sent_buffers.append(data)

    mock_sock.sendall.side_effect = capture_sendall
    mock_sock.sent_buffers = sent_buffers
    return mock_sock


def test_normalize_argv_replaces_typographic_dashes() -> None:
    """Verify normalize_argv converts typographic dashes to hyphens."""
    raw = ["\u2013p=8080", "\u2014s=127.0.0.1", "\u2013v"]
    normalized = normalize_argv(raw)
    assert normalized == ["-p=8080", "-s=127.0.0.1", "-v"]


def test_build_argument_parser() -> None:
    """Verify argument parser extracts port, host, and verbose flag."""
    parser = build_argument_parser()
    args = parser.parse_args(["-p", "9999", "-s", "127.0.0.1", "-v"])
    assert args.port == 9999
    assert args.host == "127.0.0.1"
    assert args.verbose is True


def test_parse_json_payload_variations() -> None:
    """Verify _parse_json_payload handles empty, non-dict, and valid dict payloads."""
    assert _parse_json_payload("") is None
    assert _parse_json_payload("[1, 2, 3]") is None
    assert _parse_json_payload('{"key": "value"}') == {"key": "value"}
    assert _parse_json_payload("not json") is None


def test_server_start_and_stop() -> None:
    """Verify start sets up server socket and stop cleans up resources."""
    server = SingletonProxyObserverServer(host="127.0.0.1", port=8080)
    with patch("socket.socket") as mock_sock_ctor:
        mock_server_sock = MagicMock()
        mock_sock_ctor.return_value = mock_server_sock

        server.start()
        assert server.is_running is True
        mock_server_sock.bind.assert_called_once_with(("127.0.0.1", 8080))
        mock_server_sock.listen.assert_called_once()

        server.stop()
        assert server.is_running is False
        mock_server_sock.close.assert_called_once()


def test_double_server_start_fails_gracefully() -> None:
    """Verify starting server on already bound port raises RuntimeError."""
    server = SingletonProxyObserverServer(host="127.0.0.1", port=8080)
    with patch("socket.socket") as mock_sock_ctor:
        mock_server_sock = MagicMock()
        mock_server_sock.bind.side_effect = OSError("Address already in use")
        mock_sock_ctor.return_value = mock_server_sock

        with pytest.raises(RuntimeError, match="No se pudo iniciar el servidor"):
            server.start()


def test_serve_forever_loop_and_stop() -> None:
    """Verify serve_forever accepts client connection and terminates on stop."""
    server = SingletonProxyObserverServer(host="127.0.0.1", port=8080)
    mock_server_sock = MagicMock()
    mock_client_sock = MagicMock()
    mock_client_sock.recv.return_value = b""

    def fake_accept() -> tuple[MagicMock, tuple[str, int]]:
        server.stop()
        return (mock_client_sock, ("127.0.0.1", 54321))

    mock_server_sock.accept.side_effect = fake_accept

    with patch("socket.socket", return_value=mock_server_sock):
        server.start()
        server.serve_forever()
        assert server.is_running is False


def test_acceptance_subscribe_action() -> None:
    """Acceptance test: Verify subscribe registers observer socket and creates log."""
    log_repo = CorporateLogRepository()
    log_repo.set_custom_table(None)
    proxy = CorporateDataProxy(log_repository=log_repo)
    server = SingletonProxyObserverServer(proxy=proxy, verbose=True)

    mock_obs_sock = _make_mock_client_socket(
        [b'{"ACTION": "subscribe", "UUID": "OBS-CPU-1"}\n']
    )
    server.handle_client_connection(mock_obs_sock, ("127.0.0.1", 50001))

    assert proxy.subscription_manager.get_observers_count() == 1
    mock_obs_sock.close.assert_not_called()  # Keeps socket open

    logs = log_repo.get_logs()
    sub_logs = [entry for entry in logs if entry.get("action") == "subscribe"]
    assert len(sub_logs) >= 1
    assert sub_logs[-1]["CPUid"] == "OBS-CPU-1"


def test_acceptance_set_action_and_observer_notification() -> None:
    """Acceptance test: Verify set updates data, logs action, and notifies observer."""
    data_repo = CorporateDataRepository()
    data_repo.set_custom_table(None)
    log_repo = CorporateLogRepository()
    log_repo.set_custom_table(None)
    proxy = CorporateDataProxy(log_repository=log_repo)
    server = SingletonProxyObserverServer(proxy=proxy, verbose=True)

    # Register observer first
    mock_obs_sock = _make_mock_client_socket(
        [b'{"ACTION": "subscribe", "UUID": "OBS-CPU-2"}\n']
    )
    server.handle_client_connection(mock_obs_sock, ("127.0.0.1", 50001))

    # Send SET
    req_set = {
        "UUID": "CLIENT-CPU-1",
        "ACTION": "set",
        "ID": "UADER-FCyT-IS2",
        "cp": "3260",
        "CUIT": "30-70925411-8",
        "domicilio": "25 de Mayo 385-1P",
        "localidad": "Concepción del Uruguay",
        "provincia": "Entre Rios",
        "sede": "FCyT",
        "telefono": "03442 43-1442",
        "web": "http://www.uader.edu.ar",
    }
    mock_client_set = _make_mock_client_socket([json.dumps(req_set).encode("utf-8")])
    server.handle_client_connection(mock_client_set, ("127.0.0.1", 50002))

    # Response to client
    resp_raw = b"".join(mock_client_set.sent_buffers).decode("utf-8")
    resp_obj = json.loads(resp_raw)
    assert resp_obj["id"] == "UADER-FCyT-IS2"
    assert resp_obj["sede"] == "FCyT"
    mock_client_set.close.assert_called_once()

    # Notification to observer
    obs_raw = b"".join(mock_obs_sock.sent_buffers).decode("utf-8")
    obs_event = json.loads(obs_raw)
    assert obs_event["id"] == "UADER-FCyT-IS2"

    # CorporateLog verification
    logs = log_repo.get_logs()
    set_logs = [entry for entry in logs if entry.get("action") == "set"]
    assert len(set_logs) >= 1
    assert set_logs[-1]["CPUid"] == "CLIENT-CPU-1"


def test_acceptance_get_and_list_actions() -> None:
    """Acceptance test: Verify get and list actions with audit log verification."""
    data_repo = CorporateDataRepository()
    data_repo.set_custom_table(None)
    log_repo = CorporateLogRepository()
    log_repo.set_custom_table(None)
    proxy = CorporateDataProxy(log_repository=log_repo)
    server = SingletonProxyObserverServer(proxy=proxy, verbose=True)

    # Prepopulate one item
    data_repo.put_record(
        {"id": "UADER-FCyT-IS2", "CUIT": "30-70925411-8", "sede": "FCyT"}
    )

    # 1. Action: GET
    req_get = {
        "UUID": "CLIENT-CPU-1",
        "ACTION": "get",
        "ID": "UADER-FCyT-IS2",
    }
    mock_client_get = _make_mock_client_socket([json.dumps(req_get).encode("utf-8")])
    server.handle_client_connection(mock_client_get, ("127.0.0.1", 50003))

    get_resp_raw = b"".join(mock_client_get.sent_buffers).decode("utf-8")
    get_obj = json.loads(get_resp_raw)
    assert get_obj["CUIT"] == "30-70925411-8"
    mock_client_get.close.assert_called_once()

    # 2. Action: LIST
    req_list = {
        "UUID": "CLIENT-CPU-1",
        "ACTION": "list",
    }
    mock_client_list = _make_mock_client_socket([json.dumps(req_list).encode("utf-8")])
    server.handle_client_connection(mock_client_list, ("127.0.0.1", 50004))

    list_resp_raw = b"".join(mock_client_list.sent_buffers).decode("utf-8")
    list_obj = json.loads(list_resp_raw)
    assert isinstance(list_obj, list)
    assert any(item["id"] == "UADER-FCyT-IS2" for item in list_obj)
    mock_client_list.close.assert_called_once()

    # CorporateLog verification
    logs = log_repo.get_logs()
    get_logs = [entry for entry in logs if entry.get("action") == "get"]
    list_logs = [entry for entry in logs if entry.get("action") == "list"]
    assert len(get_logs) >= 1
    assert len(list_logs) >= 1


def test_acceptance_malformed_requests_return_error() -> None:
    """Acceptance test: Server returns Error on missing.

    minimal data or malformed payload.
    """
    proxy = CorporateDataProxy()
    server = SingletonProxyObserverServer(proxy=proxy)

    def process_and_get_response(payload_bytes: bytes) -> str:
        mock_sock = _make_mock_client_socket([payload_bytes])
        server.handle_client_connection(mock_sock, ("127.0.0.1", 50000))
        return b"".join(mock_sock.sent_buffers).decode("utf-8").strip()

    # Empty payload
    assert process_and_get_response(b"") == "Error"

    # Malformed non-JSON
    assert process_and_get_response(b"NOT A JSON") == "Error"

    # Missing ACTION
    assert process_and_get_response(b'{"UUID": "123"}') == "Error"

    # Unknown ACTION
    assert process_and_get_response(b'{"UUID": "123", "ACTION": "invalid"}') == "Error"

    # GET without ID
    assert process_and_get_response(b'{"UUID": "123", "ACTION": "get"}') == "Error"

    # SET without ID
    assert (
        process_and_get_response(b'{"UUID": "123", "ACTION": "set", "sede": "FCyT"}')
        == "Error"
    )

    # GET with nonexistent ID returns Error
    req_nonexistent = b'{"UUID": "123", "ACTION": "get", "ID": "NONEXIST"}'
    assert process_and_get_response(req_nonexistent) == "Error"


def test_server_handles_proxy_exceptions_on_set_and_list() -> None:
    """Verify server returns Error when proxy operations raise unexpected exceptions."""
    proxy = CorporateDataProxy()
    server = SingletonProxyObserverServer(proxy=proxy)

    with patch.object(proxy, "set", side_effect=RuntimeError("DB write failed")):
        mock_sock = _make_mock_client_socket(
            [b'{"ACTION": "set", "ID": "1", "sede": "X"}']
        )
        server.handle_client_connection(mock_sock, ("127.0.0.1", 50000))
        assert b"".join(mock_sock.sent_buffers).decode("utf-8").strip() == "Error"

    with patch.object(proxy, "list", side_effect=RuntimeError("DB scan failed")):
        mock_sock2 = _make_mock_client_socket([b'{"ACTION": "list"}'])
        server.handle_client_connection(mock_sock2, ("127.0.0.1", 50000))
        assert b"".join(mock_sock2.sent_buffers).decode("utf-8").strip() == "Error"


def test_send_response_socket_error_handled() -> None:
    """Verify send_response_and_close handles socket errors safely."""
    server = SingletonProxyObserverServer()
    mock_sock = MagicMock()
    mock_sock.sendall.side_effect = OSError("Connection reset")
    mock_sock.close.side_effect = OSError("Close failed")

    # Should not raise exception
    server._send_response_and_close(mock_sock, {"ok": False})  # noqa: SLF001


def test_main_cli_keyboard_interrupt() -> None:
    """Verify main returns 0 on KeyboardInterrupt."""
    with (
        patch.object(SingletonProxyObserverServer, "start"),
        patch.object(
            SingletonProxyObserverServer, "serve_forever", side_effect=KeyboardInterrupt
        ),
    ):
        code = main([])
        assert code == 0


def test_main_cli_runtime_error() -> None:
    """Verify main returns 1 when start raises RuntimeError."""
    with patch.object(
        SingletonProxyObserverServer,
        "start",
        side_effect=RuntimeError("Address in use"),
    ):
        code = main([])
        assert code == 1


def test_main_cli_unexpected_exception() -> None:
    """Verify main returns 1 on unexpected exception."""
    with (
        patch.object(SingletonProxyObserverServer, "start"),
        patch.object(
            SingletonProxyObserverServer,
            "serve_forever",
            side_effect=Exception("Crash"),
        ),
    ):
        code = main([])
        assert code == 1
