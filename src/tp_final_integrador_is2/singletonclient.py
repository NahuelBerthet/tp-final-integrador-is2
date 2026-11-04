"""Cliente para consulta y actualización de datos corporativos (SingletonClient).

Este módulo implementa el cliente de terminal para interactuar con el servidor
de aplicaciones, soportando requerimientos de consulta ('get'), modificación
('set') y listado ('list') sobre CorporateData.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

LOGGER = logging.getLogger("SingletonClient")

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | dict[str, object] | list[object]
type ResponseType = dict[str, object] | list[object] | str


class SingletonClient:
    """Cliente para realizar peticiones al servidor SingletonProxyObserverTPFI.

    Permite consultar ('get'), modificar ('set') y listar ('list') registros
    centralizados de CorporateData mediante comunicación TCP por sockets.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        timeout: float = 10.0,
        *,
        verbose: bool = False,
    ) -> None:
        """Inicializa una instancia de SingletonClient.

        Args:
            host: Dirección o nombre de host del servidor de aplicaciones.
            port: Puerto TCP del servidor de aplicaciones.
            timeout: Tiempo máximo de espera en segundos para operaciones de socket.
            verbose: Indica si se deben habilitar mensajes de depuración en consola.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.verbose = verbose
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

    def load_input_file(self, file_path: str | Path) -> dict[str, object]:
        """Carga y analiza el archivo JSON de entrada.

        Args:
            file_path: Ruta al archivo JSON con el requerimiento.

        Returns:
            Diccionario con los datos leídos del archivo.

        Raises:
            FileNotFoundError: Si el archivo especificado no existe.
            TypeError: Si la estructura raíz del JSON no es un diccionario.
        """
        path = Path(file_path)
        LOGGER.debug("Leyendo archivo de entrada: %s", path)
        if not path.is_file():
            LOGGER.error("Archivo no encontrado: %s", path)
            msg = f"El archivo no existe: {path}"
            raise FileNotFoundError(msg)

        raw_content = path.read_text(encoding="utf-8")
        data: object = json.loads(raw_content)
        if not isinstance(data, dict):
            LOGGER.error("El contenido JSON no es un objeto válido")
            msg = "El JSON de entrada debe ser un objeto/diccionario."
            raise TypeError(msg)

        return data

    def prepare_payload(self, raw_data: Mapping[str, object]) -> dict[str, object]:
        """Valida y normaliza el payload del requerimiento.

        Verifica que se suministren los datos mínimos necesarios (ACTION, ID si aplica)
        e inyecta el identificador de CPU (UUID) si no se especificó o es un placeholder.

        Args:
            raw_data: Diccionario leído del archivo de entrada.

        Returns:
            Diccionario validado y normalizado listo para enviar.

        Raises:
            ValueError: Si faltan campos requeridos o la acción no es soportada.
        """
        payload: dict[str, object] = dict(raw_data)

        # Validación y normalización de ACTION
        action = payload.get("ACTION") or payload.get("action")
        if not action or not isinstance(action, str):
            LOGGER.error("Campo 'ACTION' no informado o inválido")
            msg = "Debe especificarse una acción válida ('ACTION')."
            raise ValueError(msg)

        action_clean = action.strip().lower()
        if action_clean not in {"get", "set", "list"}:
            LOGGER.error("Acción '%s' no reconocida", action)
            msg = f"Acción no soportada: '{action}'. Debe ser 'get', 'set' o 'list'."
            raise ValueError(msg)

        payload["ACTION"] = action_clean

        # Validación de ID para get y set
        record_id = payload.get("ID") or payload.get("id")
        if action_clean in {"get", "set"}:
            if not record_id or not str(record_id).strip():
                LOGGER.error("Campo 'ID' requerido para la acción '%s'", action_clean)
                msg = f"La acción '{action_clean}' requiere indicar el campo 'ID'."
                raise ValueError(msg)
            payload["ID"] = str(record_id).strip()
        elif "ID" in payload and action_clean == "list":
            # Para list no se debe requerir ni esperar ID
            LOGGER.debug("Acción 'list': se ignora ID si estaba presente")

        # Inyección o validación de UUID de CPU
        client_uuid = payload.get("UUID") or payload.get("uuid")
        if not client_uuid or str(client_uuid).strip() in {
            "",
            "XXXXXXXXXXXXXXXXXXXXXXX",
        }:
            generated_uuid = str(uuid.getnode())
            payload["UUID"] = generated_uuid
            LOGGER.debug("UUID de CPU autogenerado: %s", generated_uuid)
        else:
            payload["UUID"] = str(client_uuid).strip()

        return payload

    def send_request(self, payload: Mapping[str, object]) -> ResponseType:
        """Establece conexión TCP con el servidor y transmite el requerimiento.

        Args:
            payload: Carga útil JSON a transmitir al servidor.

        Returns:
            Respuesta decodificada del servidor (dict, list o str 'Error').

        Raises:
            ConnectionError: Si ocurre un fallo en la conexión socket TCP.
        """
        LOGGER.debug(
            "Conectando al servidor %s:%d con timeout %ss",
            self.host,
            self.port,
            self.timeout,
        )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                LOGGER.debug("Conexión establecida con éxito")

                encoded_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                sock.sendall(encoded_data)
                LOGGER.debug("Payload transmitido (%d bytes)", len(encoded_data))

                # Señalizar fin de escritura manteniendo el canal de lectura abierto
                try:
                    sock.shutdown(socket.SHUT_WR)
                except OSError:
                    LOGGER.debug("No se requirió shutdown(SHUT_WR)")

                chunks: list[bytes] = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)

                raw_response = b"".join(chunks).decode("utf-8").strip()
                LOGGER.debug("Respuesta recibida: %s", raw_response)

                if not raw_response:
                    LOGGER.warning("El servidor no retornó ninguna respuesta")
                    return "Error"

                try:
                    parsed: object = json.loads(raw_response)
                    if isinstance(parsed, (dict, list)):
                        return parsed
                    return str(parsed)
                except json.JSONDecodeError:
                    return raw_response

        except OSError as exc:
            LOGGER.exception("Fallo de comunicación por socket TCP")
            msg = f"Error al comunicar con el servidor {self.host}:{self.port}: {exc}"
            raise ConnectionError(msg) from exc

    def save_output(
        self,
        response: ResponseType,
        output_file: str | Path | None = None,
    ) -> None:
        """Emite el resultado hacia el archivo indicado o hacia la salida estándar.

        Args:
            response: Datos recibidos del servidor.
            output_file: Ruta opcional del archivo de salida.
        """
        if isinstance(response, (dict, list)):
            text = json.dumps(response, indent=4, ensure_ascii=False)
        else:
            text = str(response)

        if output_file:
            out_path = Path(output_file)
            LOGGER.debug("Grabando respuesta en archivo de salida: %s", out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text + "\n", encoding="utf-8")
        else:
            LOGGER.debug("Emitiendo respuesta por salida estándar")
            sys.stdout.write(text + "\n")
            sys.stdout.flush()

    def run(
        self,
        input_file: str | Path,
        output_file: str | Path | None = None,
    ) -> bool:
        """Ejecuta el ciclo de vida completo del cliente.

        Args:
            input_file: Ruta del archivo JSON de requerimiento.
            output_file: Ruta opcional para grabar el JSON de respuesta.

        Returns:
            True si el proceso culminó con éxito; False en caso de error.
        """
        try:
            raw_data = self.load_input_file(input_file)
            payload = self.prepare_payload(raw_data)
            response = self.send_request(payload)
            self.save_output(response, output_file)
        except Exception:
            LOGGER.exception("Error durante la ejecución de SingletonClient")
            self.save_output("Error", output_file)
            return False
        else:
            return response != "Error"


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
    """Crea y configura el analizador de argumentos para SingletonClient.

    Returns:
        Instancia de argparse.ArgumentParser debidamente configurada.
    """
    parser = argparse.ArgumentParser(
        prog="singletonclient.py",
        description="Cliente de acceso y actualización de datos corporativos (IS2).",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_file",
        required=True,
        help="Archivo JSON de entrada con la especificación del requerimiento.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_file",
        default=None,
        help="Archivo JSON opcional de salida. Si no se indica, emite a stdout.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="Activa emisión de trazas y mensajes de debug por salida estándar.",
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

    client = SingletonClient(
        host=args.server,
        port=args.port,
        verbose=args.verbose,
    )
    success = client.run(
        input_file=args.input_file,
        output_file=args.output_file,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
