"""Servidor de aplicaciones central (SingletonProxyObserverTPFI).

Integra los patrones de diseño Singleton (acceso a DynamoDB), Proxy
(gestión, auditoría y control de operaciones) y Observer (suscripción
y difusión de actualizaciones en tiempo real).
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from tp_final_integrador_is2.observer import SocketObserver
from tp_final_integrador_is2.proxy import CorporateDataProxy

if TYPE_CHECKING:
    from collections.abc import Mapping

LOGGER = logging.getLogger("SingletonProxyObserver")


def _parse_json_payload(buffer: str) -> dict[str, object] | None:
    """Intenta deserializar un payload JSON a partir de una cadena acumulada.

    Args:
        buffer: Cadena con datos recibidos por socket.

    Returns:
        Diccionario si es un objeto JSON válido, o None en caso contrario.
    """
    clean_buf = buffer.strip()
    if not clean_buf:
        return None

    decoder = json.JSONDecoder()
    try:
        parsed_obj, _ = decoder.raw_decode(clean_buf)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(parsed_obj, dict):
            return parsed_obj
        return None

    try:
        data = json.loads(clean_buf)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        LOGGER.debug("Buffer incompleto o no JSON aún: %s", clean_buf)

    return None


class SingletonProxyObserverServer:
    """Servidor TCP que implementa el backend del Trabajo Práctico Final Integrador."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        *,
        proxy: CorporateDataProxy | None = None,
        verbose: bool = False,
    ) -> None:
        """Inicializa el servidor de aplicaciones.

        Args:
            host: Interfaz de red sobre la que escuchar (default: 127.0.0.1).
            port: Puerto TCP en el que escuchar conexiones (default: 8080).
            proxy: Instancia de CorporateDataProxy (se crea una por defecto).
            verbose: Habilita trazas de depuración por salida estándar.
        """
        self.host = host
        self.port = port
        self.verbose = verbose
        self.proxy = proxy or CorporateDataProxy()
        self._server_socket: socket.socket | None = None
        self._is_running = False
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._threads_lock = threading.Lock()
        self._configure_logging()

    def _configure_logging(self) -> None:
        """Configura el logger del cliente según el modo verbose."""
        level = logging.DEBUG if self.verbose else logging.WARNING
        LOGGER.setLevel(level)
        if not LOGGER.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            )
            handler.setFormatter(formatter)
            LOGGER.addHandler(handler)
        else:
            for existing_handler in LOGGER.handlers:
                existing_handler.setLevel(level)

    @property
    def is_running(self) -> bool:
        """Indica si el servidor se encuentra actualmente en ejecución."""
        return self._is_running

    def start(self) -> None:
        """Inicia el socket servidor y comienza a aceptar conexiones TCP.

        Raises:
            RuntimeError: Si no se puede enlazar el socket (ej. puerto en uso).
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(128)
            sock.settimeout(1.0)
            self._server_socket = sock
            self._is_running = True
            LOGGER.info("Servidor escuchando en %s:%d", self.host, self.port)
        except OSError as exc:
            LOGGER.exception(
                "Fallo al iniciar el servidor en %s:%d", self.host, self.port
            )
            msg = f"No se pudo iniciar el servidor en el puerto {self.port}: {exc}"
            raise RuntimeError(msg) from exc

    def serve_forever(self) -> None:
        """Bucle principal de aceptación y despacho concurrente de conexiones."""
        if not self._is_running or self._server_socket is None:
            self.start()

        LOGGER.info("Bucle de despacho activo. Presione Ctrl+C para detener.")
        while not self._stop_event.is_set():
            if self._server_socket is None:
                break
            try:
                client_sock, client_addr = self._server_socket.accept()
                LOGGER.debug("Nueva conexión recibida desde %s", client_addr)
                thread = threading.Thread(
                    target=self.handle_client_connection,
                    args=(client_sock, client_addr),
                    daemon=True,
                )
                with self._threads_lock:
                    self._threads.append(thread)
                thread.start()
            except TimeoutError:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                LOGGER.exception("Error al aceptar conexión de cliente")

    def stop(self) -> None:
        """Detiene el servidor y libera todos los recursos asociados."""
        LOGGER.info("Deteniendo servidor...")
        self._stop_event.set()
        self._is_running = False

        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                LOGGER.debug("Error ignorado al cerrar socket servidor")
            self._server_socket = None

        # Limpiar y cerrar observadores registrados
        self.proxy.subscription_manager.clear()

    def _read_client_request(
        self, client_sock: socket.socket
    ) -> dict[str, object] | None:
        """Lee y deserializa la solicitud JSON enviada por el cliente.

        Args:
            client_sock: Socket de la conexión cliente.

        Returns:
            Diccionario de solicitud o None si los datos son inválidos o están vacíos.
        """
        client_sock.settimeout(5.0)
        buffer = ""

        while not self._stop_event.is_set():
            try:
                chunk = client_sock.recv(4096)
            except TimeoutError:
                break
            except OSError:
                return None

            if not chunk:
                break

            buffer += chunk.decode("utf-8")
            parsed = _parse_json_payload(buffer)
            if parsed is not None:
                return parsed

        return _parse_json_payload(buffer)

    def _send_response_and_close(
        self,
        client_sock: socket.socket,
        response_payload: object,
    ) -> None:
        """Transmite una respuesta JSON o texto al cliente y cierra la conexión.

        Args:
            client_sock: Socket del cliente a responder.
            response_payload: Datos a transmitir.
        """
        try:
            if isinstance(response_payload, (dict, list)):
                encoded = json.dumps(
                    response_payload,
                    indent=4,
                    ensure_ascii=False,
                ).encode("utf-8")
            else:
                encoded = str(response_payload).encode("utf-8")

            client_sock.sendall(encoded)
            try:
                client_sock.shutdown(socket.SHUT_WR)
            except OSError:
                LOGGER.debug("No se requirió shutdown en respuesta de cliente")
        except OSError as exc:
            LOGGER.warning("Error al transmitir respuesta al cliente: %s", exc)
        finally:
            try:
                client_sock.close()
            except OSError:
                LOGGER.debug("Error ignorado al cerrar socket de cliente")

    def _process_get(
        self,
        client_sock: socket.socket,
        client_uuid: str,
        request: Mapping[str, object],
    ) -> None:
        """Ejecuta la acción 'get' y responde al cliente."""
        record_id = request.get("ID") or request.get("id")
        if not record_id or not str(record_id).strip():
            LOGGER.warning("Acción 'get' sin campo ID")
            self._send_response_and_close(client_sock, "Error")
            return

        result = self.proxy.get(client_uuid, str(record_id).strip())
        response = result if result is not None else "Error"
        self._send_response_and_close(client_sock, response)

    def _process_set(
        self,
        client_sock: socket.socket,
        client_uuid: str,
        request: Mapping[str, object],
    ) -> None:
        """Ejecuta la acción 'set' y responde al cliente."""
        record_id = request.get("ID") or request.get("id")
        if not record_id or not str(record_id).strip():
            LOGGER.warning("Acción 'set' sin campo ID")
            self._send_response_and_close(client_sock, "Error")
            return

        try:
            updated_record = self.proxy.set(
                client_uuid=client_uuid,
                record_id=str(record_id).strip(),
                fields=request,
            )
            self._send_response_and_close(client_sock, updated_record)
        except Exception:
            LOGGER.exception("Error al procesar acción 'set'")
            self._send_response_and_close(client_sock, "Error")

    def _process_list(
        self,
        client_sock: socket.socket,
        client_uuid: str,
    ) -> None:
        """Ejecuta la acción 'list' y responde al cliente."""
        try:
            all_records = self.proxy.list(client_uuid)
            self._send_response_and_close(client_sock, all_records)
        except Exception:
            LOGGER.exception("Error al procesar acción 'list'")
            self._send_response_and_close(client_sock, "Error")

    def handle_client_connection(
        self,
        client_sock: socket.socket,
        client_addr: tuple[str, int],
    ) -> None:
        """Procesa una conexión entrante según la acción requerida.

        Args:
            client_sock: Socket conectado al cliente.
            client_addr: Dirección de origen del cliente.
        """
        LOGGER.debug("Procesando requerimiento de %s", client_addr)
        request = self._read_client_request(client_sock)

        if not request:
            LOGGER.warning("Solicitud vacía o malformada desde %s", client_addr)
            self._send_response_and_close(client_sock, "Error")
            return

        action_raw = request.get("ACTION") or request.get("action")
        if not action_raw or not isinstance(action_raw, str):
            LOGGER.warning("Solicitud sin acción válida desde %s", client_addr)
            self._send_response_and_close(client_sock, "Error")
            return

        action = action_raw.strip().lower()
        client_uuid = str(request.get("UUID") or request.get("uuid") or "unknown")

        LOGGER.info(
            "Acción recibida: '%s' de UUID [%s] desde %s",
            action,
            client_uuid,
            client_addr,
        )

        match action:
            case "subscribe":
                observer = SocketObserver(client_sock, client_uuid)
                self.proxy.register_subscription(client_uuid, observer)
                LOGGER.info("Socket registrado para observer [%s]", client_uuid)
            case "get":
                self._process_get(client_sock, client_uuid, request)
            case "set":
                self._process_set(client_sock, client_uuid, request)
            case "list":
                self._process_list(client_sock, client_uuid)
            case _:
                LOGGER.warning("Acción no soportada '%s'", action)
                self._send_response_and_close(client_sock, "Error")


def normalize_argv(argv: list[str]) -> list[str]:
    """Normaliza argumentos reemplazando guiones tipográficos.

    Args:
        argv: Lista original de argumentos.

    Returns:
        Lista normalizada.
    """
    normalized: list[str] = []
    dash_chars = ("\u2013", "\u2014")
    for arg in argv:
        clean = arg
        if clean.startswith(dash_chars):
            clean = "-" + clean.lstrip("\u2013\u2014")
        normalized.append(clean)
    return normalized


def build_argument_parser() -> argparse.ArgumentParser:
    """Configura el analizador de argumentos para singletonproxyobserver.py.

    Returns:
        Instancia de argparse.ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="singletonproxyobserver.py",
        description="Servidor de aplicaciones Proxy/Singleton/Observer (IS2).",
    )
    parser.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=8080,
        help="Puerto TCP del servidor (default: 8080).",
    )
    parser.add_argument(
        "-s",
        "--host",
        dest="host",
        default="127.0.0.1",
        help="Dirección de enlace o host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Activa emisión de trazas y depuración por salida estándar.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal para la ejecución del servidor.

    Args:
        argv: Lista opcional de argumentos de consola.

    Returns:
        Código de salida del proceso (0 para éxito, 1 para error).
    """
    raw_args = sys.argv[1:] if argv is None else argv
    normalized_args = normalize_argv(raw_args)

    parser = build_argument_parser()
    args = parser.parse_args(normalized_args)

    server = SingletonProxyObserverServer(
        host=args.host,
        port=args.port,
        verbose=args.verbose,
    )

    try:
        server.start()
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Cancelación manual recibida. Cerrando servidor...")
        server.stop()
        return 0
    except RuntimeError:
        LOGGER.exception("Fallo irrecuperable al iniciar servidor")
        return 1
    except Exception:
        LOGGER.exception("Excepción no controlada en el servidor")
        server.stop()
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
