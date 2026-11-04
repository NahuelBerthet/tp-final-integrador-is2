"""Gestión de acceso y actualización bajo el patrón Proxy.

Este módulo implementa el patrón Proxy para intermediar todas las operaciones
sobre CorporateData, garantizando el registro de auditoría en CorporateLog
y la activación de notificaciones a través del patrón Observer.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from tp_final_integrador_is2.database import (
    CORPORATE_DATA_FIELDS,
    CorporateDataRepository,
    CorporateLogRepository,
    get_corporate_data_repository,
    get_corporate_log_repository,
)
from tp_final_integrador_is2.observer import SubscriptionManager

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tp_final_integrador_is2.observer import ClientObserver

LOGGER = logging.getLogger("CorporateDataProxy")

type RecordsList = list[dict[str, str]]


class CorporateServiceInterface(ABC):
    """Interfaz abstracta del servicio de datos corporativos (patrón Proxy)."""

    @abstractmethod
    def get(self, client_uuid: str, record_id: str) -> dict[str, str] | None:
        """Obtiene un registro de datos corporativos."""

    @abstractmethod
    def set(
        self,
        client_uuid: str,
        record_id: str,
        fields: Mapping[str, object],
    ) -> dict[str, str]:
        """Modifica o crea un registro de datos corporativos."""

    @abstractmethod
    def list(self, client_uuid: str) -> RecordsList:
        """Lista todos los registros de datos corporativos."""


class CorporateDataService(CorporateServiceInterface):
    """Sujeto real (Real Subject) que ejecuta la lógica de negocio sobre CorporateData."""

    def __init__(self, repository: CorporateDataRepository | None = None) -> None:
        """Inicializa el servicio con el repositorio físico de datos corporativos.

        Args:
            repository: Repositorio Singleton de CorporateData.
        """
        self._repo = repository or get_corporate_data_repository()

    def get(self, client_uuid: str, record_id: str) -> dict[str, str] | None:
        """Recupera un registro por su clave identificadora.

        Args:
            client_uuid: UUID del solicitante.
            record_id: Identificador del registro buscado.

        Returns:
            Registro corporativo o None si no existe.
        """
        LOGGER.debug(
            "Service: recuperando ID [%s] para solicitante [%s]",
            record_id,
            client_uuid,
        )
        return self._repo.get_record(record_id)

    def set(
        self,
        client_uuid: str,
        record_id: str,
        fields: Mapping[str, object],
    ) -> dict[str, str]:
        """Modifica un registro existente o crea uno nuevo con campos no informados en blanco.

        Args:
            client_uuid: UUID del solicitante.
            record_id: Identificador del registro corporativo.
            fields: Campos a actualizar o asignar.

        Returns:
            Registro resultante persistido.
        """
        LOGGER.debug(
            "Service: actualizando ID [%s] para solicitante [%s]",
            record_id,
            client_uuid,
        )
        existing = self._repo.get_record(record_id)

        target_record: dict[str, str] = {}
        if existing:
            # En caso de existir, los campos no informados no se modifican
            target_record = dict(existing)
            for k, v in fields.items():
                if k not in {"ACTION", "action", "UUID", "uuid"}:
                    target_record[str(k)] = str(v)
        else:
            # Si no existiera previamente, se crea nuevo con campos no informados en blanco
            for field in CORPORATE_DATA_FIELDS:
                target_record[field] = ""
            for k, v in fields.items():
                if k not in {"ACTION", "action", "UUID", "uuid"}:
                    target_record[str(k)] = str(v)

        target_record["id"] = record_id
        return self._repo.put_record(target_record)

    def list(self, client_uuid: str) -> RecordsList:
        """Recupera todos los registros de la base.

        Args:
            client_uuid: UUID del solicitante.

        Returns:
            Lista de registros corporativos.
        """
        LOGGER.debug("Service: listando todos los registros para [%s]", client_uuid)
        return self._repo.list_records()


class CorporateDataProxy(CorporateServiceInterface):
    """Proxy que controla el acceso, audita en CorporateLog y notifica observadores."""

    def __init__(
        self,
        real_service: CorporateServiceInterface | None = None,
        log_repository: CorporateLogRepository | None = None,
        subscription_manager: SubscriptionManager | None = None,
    ) -> None:
        """Inicializa el Proxy corporativo.

        Args:
            real_service: Instancia del servicio real.
            log_repository: Repositorio Singleton para registro de auditoría.
            subscription_manager: Gestor del patrón Observer.
        """
        self._real_service = real_service or CorporateDataService()
        self._log_repo = log_repository or get_corporate_log_repository()
        self.subscription_manager = subscription_manager or SubscriptionManager()

    def get(self, client_uuid: str, record_id: str) -> dict[str, str] | None:
        """Intermedia la consulta, generando auditoría y delegando al servicio real.

        Args:
            client_uuid: Identificador de CPU del solicitante.
            record_id: Identificador del registro a consultar.

        Returns:
            Registro corporativo o None si no existe.
        """
        session_id = str(uuid.uuid4())
        LOGGER.info(
            "Proxy GET: solicitante [%s], sesión [%s], ID [%s]",
            client_uuid,
            session_id,
            record_id,
        )
        self._log_repo.log_entry(
            client_uuid=client_uuid,
            session_id=session_id,
            action="get",
            requested_id=record_id,
        )
        return self._real_service.get(client_uuid, record_id)

    def set(
        self,
        client_uuid: str,
        record_id: str,
        fields: Mapping[str, object],
    ) -> dict[str, str]:
        """Intermedia la actualización, audita, delega y difunde a observadores.

        Args:
            client_uuid: Identificador de CPU del solicitante.
            record_id: Identificador del registro objetivo.
            fields: Atributos a modificar o insertar.

        Returns:
            Registro corporativo actualizado.
        """
        session_id = str(uuid.uuid4())
        LOGGER.info(
            "Proxy SET: solicitante [%s], sesión [%s], ID [%s]",
            client_uuid,
            session_id,
            record_id,
        )
        self._log_repo.log_entry(
            client_uuid=client_uuid,
            session_id=session_id,
            action="set",
            requested_id=record_id,
        )
        updated = self._real_service.set(client_uuid, record_id, fields)

        # Difusión en tiempo real al patrón Observer
        self.subscription_manager.notify(updated)
        return updated

    def list(self, client_uuid: str) -> RecordsList:
        """Intermedia el listado completo, auditando la operación.

        Args:
            client_uuid: Identificador de CPU del solicitante.

        Returns:
            Lista completa de tuplas corporativas.
        """
        session_id = str(uuid.uuid4())
        LOGGER.info(
            "Proxy LIST: solicitante [%s], sesión [%s]",
            client_uuid,
            session_id,
        )
        self._log_repo.log_entry(
            client_uuid=client_uuid,
            session_id=session_id,
            action="list",
        )
        return self._real_service.list(client_uuid)

    def register_subscription(
        self,
        client_uuid: str,
        observer: ClientObserver,
    ) -> None:
        """Registra una suscripción en el Observer y audita en CorporateLog.

        Args:
            client_uuid: Identificador de CPU del observador.
            observer: Instancia del observador conectada por socket.
        """
        session_id = str(uuid.uuid4())
        LOGGER.info(
            "Proxy SUBSCRIBE: solicitante [%s], sesión [%s]",
            client_uuid,
            session_id,
        )
        self._log_repo.log_entry(
            client_uuid=client_uuid,
            session_id=session_id,
            action="subscribe",
        )
        self.subscription_manager.subscribe(observer)
