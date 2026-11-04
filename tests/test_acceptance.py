"""Tests de aceptación básicos automatizados del sistema TPFI IS2.

Cubren los siguientes casos de prueba:
  1. Camino feliz de cada acción (get, set, list, subscribe) con verificación
     de registros en la tabla CorporateLog.
  2. Argumentos malformados en cada programa cliente y servidor.
  3. Requerimiento sin datos mínimos necesarios.
  4. Manejo en clientes del servidor aplicativo caído.
  5. Intento de levantar dos veces el servidor de aplicaciones.
"""

from __future__ import annotations

import json
import socket
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from tp_final_integrador_is2.database import (
    CorporateDataRepository,
    CorporateLogRepository,
)
from tp_final_integrador_is2.observerclient import ObserverClient
from tp_final_integrador_is2.observerclient import main as observer_main
from tp_final_integrador_is2.proxy import CorporateDataProxy
from tp_final_integrador_is2.singletonclient import SingletonClient
from tp_final_integrador_is2.singletonclient import main as singleton_main
from tp_final_integrador_is2.singletonproxyobserver import (
    SingletonProxyObserverServer,
)
from tp_final_integrador_is2.singletonproxyobserver import (
    main as server_main,
)

# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------


def _make_mock_client_socket(chunks: list[bytes]) -> MagicMock:
    """Crea un socket simulado con fragmentos fijos de datos de entrada."""
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [*chunks, b""]
    sent_buffers: list[bytes] = []

    def _capture(data: bytes) -> None:
        sent_buffers.append(data)

    mock_sock.sendall.side_effect = _capture
    mock_sock.sent_buffers = sent_buffers
    return mock_sock


def _build_server_with_fresh_repos() -> tuple[
    SingletonProxyObserverServer,
    CorporateDataRepository,
    CorporateLogRepository,
]:
    """Construye servidor con repositorios en memoria aislados para cada test."""
    data_repo = CorporateDataRepository()
    data_repo.set_custom_table(None)
    data_repo._memory_store.clear()  # noqa: SLF001

    log_repo = CorporateLogRepository()
    log_repo.set_custom_table(None)
    log_repo._memory_logs.clear()  # noqa: SLF001

    proxy = CorporateDataProxy(log_repository=log_repo)
    server = SingletonProxyObserverServer(proxy=proxy)
    return server, data_repo, log_repo


def _send_to_server(
    server: SingletonProxyObserverServer,
    payload: dict[str, object],
) -> str:
    """Envía un payload al servidor y devuelve la respuesta como cadena."""
    raw = json.dumps(payload).encode("utf-8")
    mock_sock = _make_mock_client_socket([raw])
    server.handle_client_connection(mock_sock, ("127.0.0.1", 50000))
    return b"".join(mock_sock.sent_buffers).decode("utf-8").strip()


# ===========================================================================
# CASO 1 - Camino feliz de cada accion con verificacion en CorporateLog
# ===========================================================================


class TestCaminoFelizAcciones:
    """Verifica el flujo exitoso de cada acción del servidor."""

    def test_accion_set_crea_registro_y_loguea(self) -> None:
        """SET: inserta registro en CorporateData y genera entrada en CorporateLog."""
        server, data_repo, log_repo = _build_server_with_fresh_repos()

        payload: dict[str, object] = {
            "UUID": "CPU-SET-001",
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
        response_str = _send_to_server(server, payload)
        response = json.loads(response_str)

        # Verificar respuesta al cliente
        assert response["id"] == "UADER-FCyT-IS2"
        assert response["sede"] == "FCyT"
        assert response["CUIT"] == "30-70925411-8"

        # Verificar impacto en CorporateData (vía repositorio)
        record = data_repo.get_record("UADER-FCyT-IS2")
        assert record is not None
        assert record["sede"] == "FCyT"

        # Verificar impacto en CorporateLog
        logs = log_repo.get_logs()
        set_logs = [e for e in logs if e["action"] == "set"]
        assert len(set_logs) == 1
        assert set_logs[0]["CPUid"] == "CPU-SET-001"
        assert set_logs[0]["requested_id"] == "UADER-FCyT-IS2"
        assert "timestamp" in set_logs[0]
        assert "sessionid" in set_logs[0]

    def test_accion_get_devuelve_registro_y_loguea(self) -> None:
        """GET: recupera registro existente y genera entrada en CorporateLog."""
        server, data_repo, log_repo = _build_server_with_fresh_repos()

        # Precargar dato
        data_repo.put_record(
            {
                "id": "UADER-FCyT-IS2",
                "CUIT": "30-70925411-8",
                "sede": "FCyT",
            },
        )

        payload: dict[str, object] = {
            "UUID": "CPU-GET-001",
            "ACTION": "get",
            "ID": "UADER-FCyT-IS2",
        }
        response_str = _send_to_server(server, payload)
        response = json.loads(response_str)

        # Verificar respuesta al cliente
        assert response["id"] == "UADER-FCyT-IS2"
        assert response["CUIT"] == "30-70925411-8"

        # Verificar impacto en CorporateLog
        logs = log_repo.get_logs()
        get_logs = [e for e in logs if e["action"] == "get"]
        assert len(get_logs) == 1
        assert get_logs[0]["CPUid"] == "CPU-GET-001"
        assert get_logs[0]["requested_id"] == "UADER-FCyT-IS2"
        assert "timestamp" in get_logs[0]
        assert "sessionid" in get_logs[0]

    def test_accion_list_devuelve_todos_y_loguea(self) -> None:
        """LIST: devuelve todos los registros y genera entrada en CorporateLog."""
        server, data_repo, log_repo = _build_server_with_fresh_repos()

        data_repo.put_record({"id": "REC-001", "sede": "FCyT"})
        data_repo.put_record({"id": "REC-002", "sede": "FCA"})

        payload: dict[str, object] = {
            "UUID": "CPU-LIST-001",
            "ACTION": "list",
        }
        response_str = _send_to_server(server, payload)
        response = json.loads(response_str)

        # Verificar respuesta al cliente
        assert isinstance(response, list)
        ids = [r["id"] for r in response]
        assert "REC-001" in ids
        assert "REC-002" in ids

        # Verificar impacto en CorporateLog
        logs = log_repo.get_logs()
        list_logs = [e for e in logs if e["action"] == "list"]
        assert len(list_logs) == 1
        assert list_logs[0]["CPUid"] == "CPU-LIST-001"
        assert "timestamp" in list_logs[0]
        assert "sessionid" in list_logs[0]

    def test_accion_subscribe_registra_observer_y_loguea(self) -> None:
        """SUBSCRIBE: registra observador y genera entrada en CorporateLog."""
        server, _data_repo, log_repo = _build_server_with_fresh_repos()

        mock_obs_sock = _make_mock_client_socket(
            [
                b'{"ACTION": "subscribe", "UUID": "CPU-OBS-001"}\n',
            ],
        )
        server.handle_client_connection(mock_obs_sock, ("127.0.0.1", 50001))

        # Verificar registración del observer
        assert server.proxy.subscription_manager.get_observers_count() == 1
        mock_obs_sock.close.assert_not_called()  # Socket permanece abierto

        # Verificar impacto en CorporateLog
        logs = log_repo.get_logs()
        sub_logs = [e for e in logs if e["action"] == "subscribe"]
        assert len(sub_logs) == 1
        assert sub_logs[0]["CPUid"] == "CPU-OBS-001"
        assert "timestamp" in sub_logs[0]
        assert "sessionid" in sub_logs[0]

    def test_set_notifica_a_observer_suscripto(self) -> None:
        """SET: luego de actualizar, notifica a todos los observers suscriptos."""
        server, _data_repo, log_repo = _build_server_with_fresh_repos()

        # Suscribir observer
        mock_obs_sock = _make_mock_client_socket(
            [
                b'{"ACTION": "subscribe", "UUID": "CPU-OBS-002"}\n',
            ],
        )
        server.handle_client_connection(mock_obs_sock, ("127.0.0.1", 50001))

        # Realizar SET
        payload: dict[str, object] = {
            "UUID": "CPU-SET-002",
            "ACTION": "set",
            "ID": "UADER-FCyT-IS2",
            "sede": "FCyT",
            "telefono": "03442 43-1442",
        }
        _send_to_server(server, payload)

        # Verificar notificación enviada al observer
        obs_raw = b"".join(mock_obs_sock.sent_buffers).decode("utf-8")
        obs_event = json.loads(obs_raw)
        assert obs_event["id"] == "UADER-FCyT-IS2"
        assert obs_event["sede"] == "FCyT"

        # Verificar ambas entradas de log (subscribe + set)
        logs = log_repo.get_logs()
        actions = [e["action"] for e in logs]
        assert "subscribe" in actions
        assert "set" in actions


# ===========================================================================
# CASO 2 - Argumentos malformados en cada programa
# ===========================================================================


class TestArgumentosMalformados:
    """Verifica el manejo de argumentos inválidos en los tres programas."""

    def test_singletonclient_sin_argumento_input_retorna_error(self) -> None:
        """-i es obligatorio; sin él argparse termina con SystemExit."""
        from tp_final_integrador_is2.singletonclient import build_argument_parser

        parser = build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_singletonclient_main_con_argumento_desconocido(self) -> None:
        """Argumentos totalmente no reconocidos retornan error de sistema."""
        from tp_final_integrador_is2.singletonclient import build_argument_parser

        parser = build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--undefined-flag", "value"])

    def test_observerclient_puerto_no_numerico_falla(self) -> None:
        """Puerto no numérico provoca error de parseo con SystemExit."""
        from tp_final_integrador_is2.observerclient import build_argument_parser

        parser = build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-p", "not_a_number"])

    def test_singletonproxyobserver_puerto_no_numerico_falla(self) -> None:
        """Puerto no numérico en servidor provoca SystemExit al parsear."""
        from tp_final_integrador_is2.singletonproxyobserver import build_argument_parser

        parser = build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-p", "abc"])

    def test_singletonclient_guion_tipografico_normalizado(self) -> None:
        """Guiones tipograficos (en-dash, em-dash) se normalizan a guiones estandar."""
        from tp_final_integrador_is2.singletonclient import normalize_argv

        raw = ["\u2013i=input.json", "\u2014v", "\u2013o=out.json"]
        normalized = normalize_argv(raw)
        assert normalized == ["-i=input.json", "-v", "-o=out.json"]

    def test_observerclient_guion_tipografico_normalizado(self) -> None:
        """Guiones tipográficos en observerclient se normalizan correctamente."""
        from tp_final_integrador_is2.observerclient import normalize_argv

        raw = ["\u2013s=localhost", "\u2014p=9090"]
        normalized = normalize_argv(raw)
        assert normalized == ["-s=localhost", "-p=9090"]

    def test_singletonproxyobserver_guion_tipografico_normalizado(self) -> None:
        """Guiones tipográficos en singletonproxyobserver se normalizan correctamente."""
        from tp_final_integrador_is2.singletonproxyobserver import normalize_argv

        raw = ["\u2013p=8080", "\u2014v"]
        normalized = normalize_argv(raw)
        assert normalized == ["-p=8080", "-v"]


# ===========================================================================
# CASO 3 - Requerimiento sin datos minimos necesarios
# ===========================================================================


class TestDatosMinimosNecesarios:
    """Verifica el manejo de payloads con datos mínimos ausentes."""

    def test_servidor_payload_vacio_retorna_error(self) -> None:
        """Payload vacío recibido en servidor retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        mock_sock = _make_mock_client_socket([b""])
        server.handle_client_connection(mock_sock, ("127.0.0.1", 50000))
        response = b"".join(mock_sock.sent_buffers).decode("utf-8").strip()
        assert response == "Error"

    def test_servidor_payload_sin_accion_retorna_error(self) -> None:
        """Payload JSON sin campo ACTION retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        response = _send_to_server(server, {"UUID": "test-uuid"})
        assert response == "Error"

    def test_servidor_accion_get_sin_id_retorna_error(self) -> None:
        """GET sin campo ID en el servidor retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        response = _send_to_server(server, {"UUID": "test", "ACTION": "get"})
        assert response == "Error"

    def test_servidor_accion_set_sin_id_retorna_error(self) -> None:
        """SET sin campo ID en el servidor retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        response = _send_to_server(
            server,
            {"UUID": "test", "ACTION": "set", "sede": "FCyT"},
        )
        assert response == "Error"

    def test_servidor_accion_no_reconocida_retorna_error(self) -> None:
        """Acción no reconocida en el servidor retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        response = _send_to_server(
            server,
            {"UUID": "test", "ACTION": "delete", "ID": "1"},
        )
        assert response == "Error"

    def test_servidor_get_id_inexistente_retorna_error(self) -> None:
        """GET con ID que no existe en CorporateData retorna 'Error'."""
        server, _, _ = _build_server_with_fresh_repos()
        response = _send_to_server(
            server,
            {"UUID": "test", "ACTION": "get", "ID": "NO-EXISTE"},
        )
        assert response == "Error"

    def test_cliente_sin_action_lanza_valor_invalido(self) -> None:
        """prepare_payload lanza ValueError cuando falta el campo ACTION."""
        client = SingletonClient()
        with pytest.raises(ValueError, match="acción válida"):
            client.prepare_payload({})

    def test_cliente_get_sin_id_lanza_valor_invalido(self) -> None:
        """prepare_payload lanza ValueError cuando GET carece de campo ID."""
        client = SingletonClient()
        with pytest.raises(ValueError, match="requiere indicar el campo 'ID'"):
            client.prepare_payload({"ACTION": "get"})

    def test_cliente_set_sin_id_lanza_valor_invalido(self) -> None:
        """prepare_payload lanza ValueError cuando SET carece de campo ID."""
        client = SingletonClient()
        with pytest.raises(ValueError, match="requiere indicar el campo 'ID'"):
            client.prepare_payload({"ACTION": "set"})

    def test_cliente_accion_invalida_lanza_valor_invalido(self) -> None:
        """prepare_payload lanza ValueError para una acción no soportada."""
        client = SingletonClient()
        with pytest.raises(ValueError, match="no soportada"):
            client.prepare_payload({"ACTION": "delete", "ID": "1"})

    def test_cliente_archivo_inexistente_lanza_file_not_found(
        self,
        tmp_path: Path,
    ) -> None:
        """load_input_file lanza FileNotFoundError cuando el archivo no existe."""
        client = SingletonClient()
        with pytest.raises(FileNotFoundError):
            client.load_input_file(tmp_path / "noexiste.json")

    def test_cliente_json_malformado_lanza_error(self, tmp_path: Path) -> None:
        """load_input_file lanza JSONDecodeError para JSON malformado."""
        import json

        bad = tmp_path / "bad.json"
        bad.write_text("{sin_comillas: valor", encoding="utf-8")
        client = SingletonClient()
        with pytest.raises(json.JSONDecodeError):
            client.load_input_file(bad)


# ===========================================================================
# CASO 4 - Manejo en clientes de servidor aplicativo caido
# ===========================================================================


class TestServidorCaido:
    """Verifica el comportamiento de los clientes cuando el servidor no responde."""

    def test_singletonclient_servidor_caido_retorna_false_y_error(
        self,
        tmp_path: Path,
    ) -> None:
        """SingletonClient.run() retorna False y escribe 'Error' cuando el servidor no responde."""
        in_file = tmp_path / "req.json"
        in_file.write_text(
            json.dumps({"ACTION": "list"}),
            encoding="utf-8",
        )
        out_file = tmp_path / "resp.json"

        # Puerto 59998 no debe tener nada escuchando en el sandbox
        client = SingletonClient(host="127.0.0.1", port=59998, timeout=2.0)
        success = client.run(in_file, out_file)

        assert success is False
        assert out_file.read_text(encoding="utf-8").strip() == "Error"

    def test_singletonclient_main_servidor_caido_retorna_codigo_1(
        self,
        tmp_path: Path,
    ) -> None:
        """main() de SingletonClient retorna código 1 cuando el servidor está caído."""
        in_file = tmp_path / "req.json"
        in_file.write_text(json.dumps({"ACTION": "list"}), encoding="utf-8")
        out_file = tmp_path / "resp.json"

        code = singleton_main(
            [
                "-i",
                str(in_file),
                "-o",
                str(out_file),
                "-p",
                "59998",
                "-s",
                "127.0.0.1",
            ],
        )
        assert code == 1

    def test_singletonclient_send_request_levanta_connection_error(self) -> None:
        """send_request levanta ConnectionError cuando la conexión es rechazada."""
        client = SingletonClient(host="127.0.0.1", port=59997, timeout=1.0)
        with patch("socket.socket") as mock_sock_ctor:
            mock_socket = MagicMock()
            mock_socket.connect.side_effect = OSError("Connection refused")
            mock_sock_ctor.return_value.__enter__.return_value = mock_socket

            with pytest.raises(ConnectionError, match="Connection refused"):
                client.send_request({"ACTION": "list"})

    def test_observerclient_servidor_caido_reintenta_con_limite(self) -> None:
        """ObserverClient.run() reintenta la reconexión hasta el límite indicado."""
        client = ObserverClient(host="127.0.0.1", port=59996, retry_interval=0.01)

        with patch("socket.socket") as mock_sock_ctor:
            mock_socket = MagicMock()
            mock_socket.connect.side_effect = OSError("Connection refused")
            mock_sock_ctor.return_value.__enter__.return_value = mock_socket

            # max_reconnects=2 → reintentar solo 2 veces y terminar
            client.run(max_reconnects=2)
            assert mock_socket.connect.call_count == 2

    def test_observerclient_main_servidor_caido_retorna_codigo_0(self) -> None:
        """main() de ObserverClient retorna 0 tras reconexiones agotadas."""
        with patch("socket.socket") as mock_sock_ctor:
            mock_socket = MagicMock()
            mock_socket.connect.side_effect = OSError("Connection refused")
            mock_sock_ctor.return_value.__enter__.return_value = mock_socket

            # max_reconnects no expuesto por main, se detiene con KeyboardInterrupt
            with patch.object(ObserverClient, "run", side_effect=KeyboardInterrupt):
                code = observer_main(["-p", "59996", "-s", "127.0.0.1"])
                assert code == 0


# ===========================================================================
# CASO 5 - Intento de levantar dos veces el servidor de aplicaciones
# ===========================================================================


class TestDobleArranqueServidor:
    """Verifica que no es posible iniciar dos instancias del servidor en el mismo puerto."""

    def test_segundo_start_en_mismo_puerto_lanza_runtime_error(self) -> None:
        """start() falla con RuntimeError cuando el puerto ya está en uso."""
        server = SingletonProxyObserverServer(host="127.0.0.1", port=8080)

        with patch("socket.socket") as mock_sock_ctor:
            mock_server_sock = MagicMock()
            mock_server_sock.bind.side_effect = OSError("Address already in use")
            mock_sock_ctor.return_value = mock_server_sock

            with pytest.raises(RuntimeError, match="No se pudo iniciar el servidor"):
                server.start()

    def test_main_servidor_runtime_error_retorna_codigo_1(self) -> None:
        """main() retorna código 1 cuando start() lanza RuntimeError."""
        with patch.object(
            SingletonProxyObserverServer,
            "start",
            side_effect=RuntimeError("Address already in use"),
        ):
            code = server_main([])
            assert code == 1

    def test_dos_servidores_distintas_instancias_primer_falla(self) -> None:
        """Simula arranque de dos servidores:el segundo falla.

        al bindear el mismo puerto.
        """
        server_a = SingletonProxyObserverServer(host="127.0.0.1", port=8080)
        server_b = SingletonProxyObserverServer(host="127.0.0.1", port=8080)

        call_count = 0

        def bind_side_effect(_addr: tuple[str, int]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                msg = "Address already in use"
                raise OSError(msg)

        with patch("socket.socket") as mock_sock_ctor:
            mock_sock = MagicMock()
            mock_sock.bind.side_effect = bind_side_effect
            mock_sock_ctor.return_value = mock_sock

            server_a.start()
            assert server_a.is_running is True

            with pytest.raises(RuntimeError, match="No se pudo iniciar el servidor"):
                server_b.start()

            assert server_b.is_running is False

        server_a.stop()
