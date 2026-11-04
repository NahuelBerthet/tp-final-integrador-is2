"""Cliente observador para notificaciones en tiempo real (ObserverClient).

Este módulo implementa el cliente subscripto al servidor de aplicaciones,
manteniendo una conexión TCP abierta para recibir notificaciones cada vez
que se actualicen los datos en CorporateData.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

LOGGER = logging.getLogger("ObserverClient")


class ObserverClient:
    """Cliente observador que escucha cambios en la base de datos corporativa.

    Se conecta mediante socket TCP al servidor SingletonProxyObserverTPFI,
    se subscribe enviando su identificador de CPU y permanece a la escucha
    de notificaciones emitidas tras cada actualización en CorporateData.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        retry_interval: float = 30.0,
        *,
        verbose: bool = False,
    ) -> None:
        """Inicializa una instancia de ObserverClient.

        Args:
            host: Dirección o nombre de host del servidor de aplicaciones.
            port: Puerto TCP del servidor de aplicaciones.
            retry_interval: Tiempo de espera en segundos entre reintentos de conexión.
            verbose: Indica si se deben habilitar mensajes de depuración en consola.
        """
        self.host = host
        self.port = port
        self.retry_interval = retry_interval
        self.verbose = verbose
        self._stop_event = threading.Event()
        self._current_socket: socket.socket | None = None
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

    def build_subscription_payload(self) -> dict[str, str]:
        """Construye el payload JSON para la suscripción del observador.

        Returns:
            Diccionario con la identificación de CPU (UUID) y la acción 'subscribe'.
        """
        cpu_uuid = str(uuid.getnode())
        LOGGER.debug("Generando payload de suscripción con UUID de CPU: %s", cpu_uuid)
        return {
            "UUID": cpu_uuid,
            "ACTION": "subscribe",
        }

    def handle_notification(
        self,
        notification: object,
        output_file: str | Path | None = None,
    ) -> None:
        """Muestra la notificación recibida por stdout y en archivo si se configuró.

        Args:
            notification: Objeto deserializado o texto de la notificación recibida.
            output_file: Ruta opcional de archivo para persistir la notificación.
        """
        if isinstance(notification, (dict, list)):
            formatted = json.dumps(notification, indent=4, ensure_ascii=False)
        else:
            formatted = str(notification)

        LOGGER.debug("Notificación procesada exitosamente")
        # Mostrar por salida estándar
        sys.stdout.write(formatted + "\n")
        sys.stdout.flush()

        # Grabar en archivo de salida si fue especificado
        if output_file:
            path = Path(output_file)
            LOGGER.debug("Guardando notificación en archivo: %s", path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(formatted + "\n", encoding="utf-8")

    def connect_and_listen(
        self,
        output_file: str | Path | None = None,
        max_messages: int | None = None,
    ) -> int:
        """Conecta al servidor, envía la suscripción y escucha eventos entrantes.

        Args:
            output_file: Ruta opcional para grabar notificaciones.
            max_messages: Límite opcional de mensajes a recibir (útil para pruebas).

        Returns:
            Cantidad de notificaciones recibidas y procesadas.

        Raises:
            ConnectionError: Si se interrumpe o falla la conexión socket.
        """
        payload = self.build_subscription_payload()
        decoder = json.JSONDecoder()
        received_count = 0

        LOGGER.debug("Intentando conectar con %s:%d", self.host, self.port)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                self._current_socket = sock
                sock.connect((self.host, self.port))
                LOGGER.info(
                    "Conexión establecida con el servidor %s:%d", self.host, self.port
                )

                # Transmitir requerimiento de suscripción
                data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                sock.sendall(data)
                LOGGER.debug("Solicitud de suscripción enviada")

                buffer = ""
                while not self._stop_event.is_set():
                    sock.settimeout(1.0)
                    try:
                        chunk = sock.recv(4096)
                    except TimeoutError:
                        continue

                    if not chunk:
                        LOGGER.warning("El servidor cerró la conexión TCP")
                        msg = "Conexión TCP finalizada por el servidor."
                        raise ConnectionResetError(msg)

                    buffer += chunk.decode("utf-8")
                    while buffer and not self._stop_event.is_set():
                        buffer = buffer.lstrip()
                        if not buffer:
                            break
                        try:
                            obj: object
                            obj, index = decoder.raw_decode(buffer)
                            buffer = buffer[index:].lstrip()
                            self.handle_notification(obj, output_file)
                            received_count += 1
                            if (
                                max_messages is not None
                                and received_count >= max_messages
                            ):
                                return received_count
                        except json.JSONDecodeError:
                            # Datos incompletos en el buffer, continuar leyendo del socket
                            break
        except OSError as exc:
            LOGGER.exception("Error en socket TCP durante la suscripción/escucha")
            msg = f"Fallo de conexión con {self.host}:{self.port}: {exc}"
            raise ConnectionError(msg) from exc
        finally:
            self._current_socket = None

        return received_count

    @property
    def is_stopped(self) -> bool:
        """Indica si se solicitó la detención del observador.

        Returns:
            True si el evento de detención está activo; False en caso contrario.
        """
        return self._stop_event.is_set()

    def stop(self) -> None:
        """Solicita la detención inmediata del observador."""
        LOGGER.info("Señalando detención del observador...")
        self._stop_event.set()
        if self._current_socket:
            try:
                self._current_socket.close()
            except OSError:
                LOGGER.debug("Excepción ignorada al cerrar socket")

    def run(
        self,
        output_file: str | Path | None = None,
        max_reconnects: int | None = None,
        max_messages: int | None = None,
    ) -> None:
        """Inicia el bucle principal con reconexión automática periódica.

        Args:
            output_file: Ruta opcional de archivo para guardar notificaciones.
            max_reconnects: Límite opcional de reintentos (None para infinito).
            max_messages: Límite opcional de mensajes a recibir en total.
        """
        reconnect_attempts = 0
        total_messages = 0

        LOGGER.info("Iniciando ObserverClient sobre %s:%d", self.host, self.port)
        while not self._stop_event.is_set():
            try:
                remaining_messages = (
                    None if max_messages is None else (max_messages - total_messages)
                )
                count = self.connect_and_listen(
                    output_file=output_file,
                    max_messages=remaining_messages,
                )
                total_messages += count
                if max_messages is not None and total_messages >= max_messages:
                    LOGGER.info("Límite de mensajes alcanzado (%d)", total_messages)
                    break
            except ConnectionError as exc:
                reconnect_attempts += 1
                LOGGER.warning("Error de conexión: %s", exc)
                if max_reconnects is not None and reconnect_attempts >= max_reconnects:
                    LOGGER.info(
                        "Límite de reintentos alcanzado (%d)", reconnect_attempts
                    )
                    break
                if not self._stop_event.is_set():
                    LOGGER.info(
                        "Reintentando conexión en %.1f segundos...",
                        self.retry_interval,
                    )
                    self._stop_event.wait(self.retry_interval)
            except Exception:
                LOGGER.exception("Excepción no recuperable en ObserverClient")
                raise


def normalize_argv(argv: list[str]) -> list[str]:
    """Normaliza argumentos de línea de comandos reemplazando guiones tipográficos.

    Args:
        argv: Lista original de argumentos de línea de comandos.

    Returns:
        Lista de argumentos normalizada con guiones estándar '-'.
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
    """Crea y configura el analizador de argumentos para ObserverClient.

    Returns:
        Instancia de argparse.ArgumentParser debidamente configurada.
    """
    parser = argparse.ArgumentParser(
        prog="observerclient.py",
        description="Cliente observador de eventos de CorporateData (IS2).",
    )
    parser.add_argument(
        "-s",
        "--server",
        dest="server",
        default="localhost",
        help="Nombre de host o IP del servidor (default: localhost).",
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
        "-o",
        "--output",
        dest="output_file",
        default=None,
        help="Archivo JSON opcional de salida para persistir notificaciones.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Activa emisión de trazas y mensajes de debug por salida estándar.",
    )
    parser.add_argument(
        "-r",
        "--retry-interval",
        dest="retry_interval",
        type=float,
        default=30.0,
        help="Intervalo en segundos entre reintentos de conexión (default: 30.0).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal para la ejecución desde línea de comandos.

    Args:
        argv: Lista opcional de argumentos de consola (usa sys.argv[1:] por defecto).

    Returns:
        Código de salida del proceso (0 para éxito, 1 para error).
    """
    raw_args = sys.argv[1:] if argv is None else argv
    normalized_args = normalize_argv(raw_args)

    parser = build_argument_parser()
    args = parser.parse_args(normalized_args)

    client = ObserverClient(
        host=args.server,
        port=args.port,
        retry_interval=args.retry_interval,
        verbose=args.verbose,
    )

    try:
        client.run(output_file=args.output_file)
    except KeyboardInterrupt:
        LOGGER.info("Cancelación manual recibida. Finalizando ObserverClient...")
        client.stop()
        return 0
    except Exception:
        LOGGER.exception("Finalización anormal por excepción")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
