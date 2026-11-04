"""Unit tests for SingletonClient."""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from tp_final_integrador_is2.singletonclient import (
    SingletonClient,
    build_argument_parser,
    main,
    normalize_argv,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_normalize_argv_replaces_typographic_dashes() -> None:
    """Verify normalize_argv converts en-dash and em-dash to hyphen."""
    raw = ["\u2013i=input.json", "\u2014o=output.json", "\u2013v", "-s=localhost"]
    normalized = normalize_argv(raw)
    assert normalized == ["-i=input.json", "-o=output.json", "-v", "-s=localhost"]


def test_argument_parser_valid_args() -> None:
    """Verify argument parser extracts options properly."""
    parser = build_argument_parser()
    args = parser.parse_args(
        ["-i", "input.json", "-o", "out.json", "-v", "-s", "server", "-p", "9000"],
    )
    assert args.input_file == "input.json"
    assert args.output_file == "out.json"
    assert args.verbose is True
    assert args.server == "server"
    assert args.port == 9000


def test_argument_parser_missing_required_input() -> None:
    """Verify argument parser errors when -i is missing."""
    parser = build_argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_prepare_payload_success_get() -> None:
    """Verify prepare_payload normalizes a valid 'get' request."""
    client = SingletonClient()
    raw = {"ACTION": "GET", "ID": "UADER-123", "UUID": "custom-uuid"}
    result = client.prepare_payload(raw)
    assert result["ACTION"] == "get"
    assert result["ID"] == "UADER-123"
    assert result["UUID"] == "custom-uuid"


def test_prepare_payload_autogenerates_uuid_when_placeholder_or_missing() -> None:
    """Verify CPU UUID is generated when empty, omitted, or placeholder."""
    client = SingletonClient()
    raw_missing: dict[str, object] = {"action": "list"}
    payload1 = client.prepare_payload(raw_missing)
    assert payload1["UUID"] != ""
    assert payload1["UUID"] != "XXXXXXXXXXXXXXXXXXXXXXX"

    raw_placeholder = {"action": "list", "UUID": "XXXXXXXXXXXXXXXXXXXXXXX"}
    payload2 = client.prepare_payload(raw_placeholder)
    assert payload2["UUID"] != "XXXXXXXXXXXXXXXXXXXXXXX"


def test_prepare_payload_invalid_action() -> None:
    """Verify prepare_payload rejects missing or unknown actions."""
    client = SingletonClient()
    with pytest.raises(ValueError, match="Debe especificarse una acción válida"):
        client.prepare_payload({})

    with pytest.raises(ValueError, match="Acción no soportada"):
        client.prepare_payload({"ACTION": "delete"})


def test_prepare_payload_missing_id_for_get_and_set() -> None:
    """Verify prepare_payload requires ID for get and set operations."""
    client = SingletonClient()
    with pytest.raises(ValueError, match="requiere indicar el campo 'ID'"):
        client.prepare_payload({"ACTION": "get"})

    with pytest.raises(ValueError, match="requiere indicar el campo 'ID'"):
        client.prepare_payload({"ACTION": "set", "ID": "   "})


def test_prepare_payload_list_ignores_id() -> None:
    """Verify list action accepts payload even without ID."""
    client = SingletonClient()
    payload = client.prepare_payload({"ACTION": "list", "ID": "not-needed"})
    assert payload["ACTION"] == "list"


def test_load_input_file_not_found(tmp_path: Path) -> None:
    """Verify FileNotFoundError is raised when file does not exist."""
    client = SingletonClient()
    with pytest.raises(FileNotFoundError):
        client.load_input_file(tmp_path / "nonexistent.json")


def test_load_input_file_invalid_json(tmp_path: Path) -> None:
    """Verify json.JSONDecodeError is raised for malformed JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not a json", encoding="utf-8")
    client = SingletonClient()
    with pytest.raises(json.JSONDecodeError):
        client.load_input_file(bad_file)


def test_load_input_file_not_a_dict(tmp_path: Path) -> None:
    """Verify TypeError is raised when JSON root is not an object."""
    list_file = tmp_path / "list.json"
    list_file.write_text("[1, 2, 3]", encoding="utf-8")
    client = SingletonClient()
    with pytest.raises(TypeError):
        client.load_input_file(list_file)


def test_send_request_success_json_response() -> None:
    """Verify send_request sends JSON bytes and parses JSON response."""
    client = SingletonClient(host="127.0.0.1", port=8080)
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b'{"status": "ok", "id": "1"}', b""]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        response = client.send_request({"ACTION": "get", "ID": "1"})
        assert response == {"status": "ok", "id": "1"}
        mock_socket.connect.assert_called_once_with(("127.0.0.1", 8080))


def test_send_request_shutdown_oserror_handled() -> None:
    """Verify send_request handles OSError on shutdown gracefully."""
    client = SingletonClient()
    mock_socket = MagicMock()
    mock_socket.shutdown.side_effect = OSError("Socket not connected")
    mock_socket.recv.side_effect = [b'{"ok": true}', b""]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        response = client.send_request({"ACTION": "list"})
        assert response == {"ok": True}


def test_send_request_primitive_and_non_json_response() -> None:
    """Verify send_request handles primitive JSON values and non-JSON strings."""
    client = SingletonClient()
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b"123", b""]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        assert client.send_request({"ACTION": "list"}) == "123"

    mock_socket_raw = MagicMock()
    mock_socket_raw.recv.side_effect = [b"Error string", b""]
    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket_raw
        assert client.send_request({"ACTION": "list"}) == "Error string"


def test_send_request_empty_response_returns_error() -> None:
    """Verify send_request returns 'Error' when server returns nothing."""
    client = SingletonClient()
    mock_socket = MagicMock()
    mock_socket.recv.side_effect = [b""]

    with patch("socket.socket") as mock_socket_ctor:
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket
        response = client.send_request({"ACTION": "get", "ID": "1"})
        assert response == "Error"


def test_send_request_connection_error_raises_exception() -> None:
    """Verify send_request wraps OSError into ConnectionError."""
    client = SingletonClient()
    with patch("socket.socket") as mock_socket_ctor:
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = OSError("Connection refused")
        mock_socket_ctor.return_value.__enter__.return_value = mock_socket

        with pytest.raises(ConnectionError, match="Connection refused"):
            client.send_request({"ACTION": "list"})


def test_save_output_to_stdout_and_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify save_output writes to stdout when no file, and writes to file when given."""
    client = SingletonClient()
    payload: dict[str, object] = {"key": "value"}

    # To stdout
    client.save_output(payload, None)
    captured = capsys.readouterr()
    assert '"key": "value"' in captured.out

    # To file
    out_file = tmp_path / "subdir" / "output.json"
    client.save_output(payload, out_file)
    assert out_file.is_file()
    assert json.loads(out_file.read_text(encoding="utf-8")) == payload


def test_run_success_flow(tmp_path: Path) -> None:
    """Verify run execution succeeds with valid input and mock server response."""
    in_file = tmp_path / "req.json"
    in_file.write_text(
        json.dumps({"ACTION": "get", "ID": "UADER-FCyT-IS2"}),
        encoding="utf-8",
    )
    out_file = tmp_path / "resp.json"

    client = SingletonClient()
    with patch.object(
        client,
        "send_request",
        return_value={"id": "UADER-FCyT-IS2", "sede": "FCyT"},
    ):
        success = client.run(in_file, out_file)
        assert success is True
        assert out_file.is_file()
        content = json.loads(out_file.read_text(encoding="utf-8"))
        assert content["sede"] == "FCyT"


def test_run_handles_exception_and_writes_error(tmp_path: Path) -> None:
    """Verify run returns False and writes Error on failure."""
    in_file = tmp_path / "broken.json"
    in_file.write_text("{malformed", encoding="utf-8")
    out_file = tmp_path / "error.json"

    client = SingletonClient(verbose=True)
    success = client.run(in_file, out_file)
    assert success is False
    assert out_file.read_text(encoding="utf-8").strip() == "Error"


def test_main_cli_success(tmp_path: Path) -> None:
    """Verify main returns 0 on successful run."""
    in_file = tmp_path / "req.json"
    in_file.write_text(
        json.dumps({"ACTION": "list"}),
        encoding="utf-8",
    )
    out_file = tmp_path / "resp.json"

    with patch.object(
        SingletonClient,
        "send_request",
        return_value=[{"id": "item1"}],
    ):
        code = main(["-i", str(in_file), "-o", str(out_file), "-v"])
        assert code == 0
        assert json.loads(out_file.read_text(encoding="utf-8")) == [{"id": "item1"}]


def test_main_cli_server_down(tmp_path: Path) -> None:
    """Verify main returns 1 and outputs Error when server connection fails."""
    in_file = tmp_path / "req.json"
    in_file.write_text(
        json.dumps({"ACTION": "list"}),
        encoding="utf-8",
    )
    out_file = tmp_path / "resp.json"

    # Attempt to connect to port that has nothing listening
    code = main(["-i", str(in_file), "-o", str(out_file), "-p", "59999"])
    assert code == 1
    assert out_file.read_text(encoding="utf-8").strip() == "Error"
