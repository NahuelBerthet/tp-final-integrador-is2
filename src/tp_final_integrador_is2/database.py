"""Acceso físico a DynamoDB bajo el patrón Singleton.

Este módulo implementa el acceso físico a las tablas CorporateData y
CorporateLog en AWS DynamoDB mediante instancias Singleton thread-safe.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar, Protocol, Self

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from collections.abc import Mapping


class DynamoTable(Protocol):
    """Protocolo estructural para representar un recurso Table de DynamoDB."""

    def get_item(self, **kwargs: object) -> dict[str, object]:
        """Obtiene un item de la tabla."""
        ...

    def put_item(self, **kwargs: object) -> dict[str, object]:
        """Guarda un item en la tabla."""
        ...

    def scan(self, **kwargs: object) -> dict[str, object]:
        """Escanea todos los items de la tabla."""
        ...


LOGGER = logging.getLogger("DatabaseSingleton")

CORPORATE_DATA_FIELDS: tuple[str, ...] = (
    "id",
    "cp",
    "CUIT",
    "domicilio",
    "idreq",
    "idSeq",
    "localidad",
    "provincia",
    "sede",
    "seqID",
    "telefono",
    "web",
)


class CorporateDataRepository:
    """Singleton para el acceso físico a la tabla DynamoDB 'CorporateData'."""

    _instance: Self | None = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> Self:
        """Garantiza la existencia de una única instancia de la clase."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Inicializa la conexión con DynamoDB si no fue inicializada previamente."""
        if self._initialized:
            return
        self._table: DynamoTable | None = None
        self._memory_store: dict[str, dict[str, str]] = {}
        self._use_memory_fallback = False
        self._init_table()
        self._initialized = True

    def _init_table(self) -> None:
        """Inicializa el recurso DynamoDB Table para CorporateData."""
        try:
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table("CorporateData")
            _ = table.table_name
            self._table = table
            LOGGER.info("Conectado exitosamente a la tabla DynamoDB CorporateData")
        except Exception as exc:
            LOGGER.warning(
                "No se pudo conectar a CorporateData (%s). Usando fallback local.",
                exc,
            )
            self._use_memory_fallback = True

    def set_custom_table(self, table: DynamoTable | None) -> None:
        """Permite inyectar una tabla simulada para pruebas.

        Args:
            table: Objeto tabla DynamoDB o None para memoria local.
        """
        self._table = table
        self._use_memory_fallback = table is None

    def get_record(self, record_id: str) -> dict[str, str] | None:
        """Recupera un registro de CorporateData a partir de su ID.

        Args:
            record_id: Identificador único del registro a consultar.

        Returns:
            Diccionario con los datos del registro o None si no existe.

        Raises:
            RuntimeError: Si ocurre un fallo crítico al consultar la base.
        """
        if self._use_memory_fallback or self._table is None:
            LOGGER.debug(
                "Recuperando registro '%s' desde almacén en memoria", record_id
            )
            return self._memory_store.get(record_id)

        try:
            response = self._table.get_item(Key={"id": record_id})
            item = response.get("Item")
        except ClientError as exc:
            LOGGER.exception("Error al consultar CorporateData en DynamoDB")
            msg = f"Fallo al consultar registro en CorporateData: {exc}"
            raise RuntimeError(msg) from exc
        else:
            if isinstance(item, dict):
                return {str(k): str(v) for k, v in item.items()}
            return None

    def put_record(self, record: Mapping[str, object]) -> dict[str, str]:
        """Inserta o actualiza un registro en CorporateData.

        Args:
            record: Diccionario con los campos del registro corporativo.

        Returns:
            Registro almacenado como diccionario de cadenas.

        Raises:
            RuntimeError: Si ocurre un fallo crítico al escribir en DynamoDB.
            ValueError: Si el registro carece de campo 'id'.
        """
        record_id = str(record.get("id") or record.get("ID") or "").strip()
        if not record_id:
            msg = "El registro a almacenar debe contener el campo 'id'."
            raise ValueError(msg)

        clean_record: dict[str, str] = {str(k): str(v) for k, v in record.items()}
        clean_record["id"] = record_id

        if self._use_memory_fallback or self._table is None:
            LOGGER.debug("Grabando registro '%s' en almacén en memoria", record_id)
            self._memory_store[record_id] = clean_record
            return clean_record

        try:
            self._table.put_item(Item=clean_record)
            LOGGER.debug("Registro '%s' guardado exitosamente en DynamoDB", record_id)
        except ClientError as exc:
            LOGGER.exception("Error al escribir registro en CorporateData")
            msg = f"Fallo al escribir en CorporateData: {exc}"
            raise RuntimeError(msg) from exc
        else:
            return clean_record

    def list_records(self) -> list[dict[str, str]]:
        """Recupera todos los registros existentes en CorporateData.

        Returns:
            Lista con todos los tuples de la tabla.

        Raises:
            RuntimeError: Si ocurre un fallo durante el scan de DynamoDB.
        """
        if self._use_memory_fallback or self._table is None:
            LOGGER.debug("Listando registros desde almacén en memoria")
            return list(self._memory_store.values())

        try:
            response = self._table.scan()
            items = response.get("Items", [])
        except ClientError as exc:
            LOGGER.exception("Error al escanear CorporateData en DynamoDB")
            msg = f"Fallo al listar registros en CorporateData: {exc}"
            raise RuntimeError(msg) from exc
        else:
            raw_items = response.get("Items", [])
            items = raw_items if isinstance(raw_items, list) else []
            return [
                {str(k): str(v) for k, v in item.items()}
                for item in items
                if isinstance(item, dict)
            ]


class CorporateLogRepository:
    """Singleton para el acceso físico a la tabla DynamoDB 'CorporateLog'."""

    _instance: Self | None = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> Self:
        """Garantiza una única instancia de la clase."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Inicializa la conexión con DynamoDB para la tabla de auditoría."""
        if self._initialized:
            return
        self._table: DynamoTable | None = None
        self._memory_logs: list[dict[str, str]] = []
        self._use_memory_fallback = False
        self._init_table()
        self._initialized = True

    def _init_table(self) -> None:
        """Inicializa el recurso DynamoDB Table para CorporateLog."""
        try:
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table("CorporateLog")
            _ = table.table_name
            self._table = table
            LOGGER.info("Conectado exitosamente a la tabla DynamoDB CorporateLog")
        except Exception as exc:
            LOGGER.warning(
                "No se pudo conectar a CorporateLog (%s). Usando fallback local.",
                exc,
            )
            self._use_memory_fallback = True

    def set_custom_table(self, table: DynamoTable | None) -> None:
        """Permite inyectar una tabla simulada para pruebas.

        Args:
            table: Objeto tabla DynamoDB o None para memoria local.
        """
        self._table = table
        self._use_memory_fallback = table is None

    def log_entry(
        self,
        client_uuid: str,
        session_id: str,
        action: str,
        requested_id: str | None = None,
    ) -> dict[str, str]:
        """Inserta un registro de auditoría en CorporateLog.

        Args:
            client_uuid: Identificador de CPU del solicitante.
            session_id: Identificador único de sesión.
            action: Acción solicitada ('get', 'set', 'list', 'subscribe').
            requested_id: Identificador del registro objetivo si aplica.

        Returns:
            Diccionario con la entrada de log registrada.

        Raises:
            RuntimeError: Si ocurre un error al persistir el registro de log.
        """
        log_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        entry: dict[str, str] = {
            "id": log_id,
            "CPUid": client_uuid,
            "UUID": client_uuid,
            "sessionid": session_id,
            "action": action,
            "timestamp": ts,
        }
        if requested_id is not None:
            entry["requested_id"] = requested_id

        if self._use_memory_fallback or self._table is None:
            LOGGER.debug("Guardando log en memoria: %s", entry)
            self._memory_logs.append(entry)
            return entry

        try:
            self._table.put_item(Item=entry)
            LOGGER.debug("Log registrado exitosamente en DynamoDB CorporateLog")
        except ClientError as exc:
            LOGGER.exception("Error al registrar log en DynamoDB CorporateLog")
            msg = f"Fallo al registrar entrada en CorporateLog: {exc}"
            raise RuntimeError(msg) from exc
        else:
            return entry

    def get_logs(self) -> list[dict[str, str]]:
        """Recupera los logs almacenados en memoria (útil para aserciones en pruebas).

        Returns:
            Lista con las entradas de log registradas.
        """
        return list(self._memory_logs)


def get_corporate_data_repository() -> CorporateDataRepository:
    """Función de acceso Singleton para la tabla CorporateData.

    Returns:
        Instancia única de CorporateDataRepository.
    """
    return CorporateDataRepository()


def get_corporate_log_repository() -> CorporateLogRepository:
    """Función de acceso Singleton para la tabla CorporateLog.

    Returns:
        Instancia única de CorporateLogRepository.
    """
    return CorporateLogRepository()
