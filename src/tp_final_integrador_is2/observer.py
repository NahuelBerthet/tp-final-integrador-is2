"""Gestión de subscripciones bajo el patrón Observer.

Este módulo implementa el patrón Observer para mantener el registro de
clientessubscriptos y difundir en tiempo real las
actualizaciones producidas sobre CorporateData.
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import socket
    from collections.abc import Mapping

LOGGER = logging.getLogger("SubscriptionObserver")


class ClientObserver(ABC):
    """Interfaz abstracta para los observadores de eventos de CorporateData."""

    @abstractmethod
    def update(self, event: Mapping[str, object]) -> bool:
        """Recibe y procesa una notificación de evento corporativo.

        Args:
            event: Datos del evento corporativo.

        Returns:
            True si la entrega fue exitosa; False en caso de fallo o socket cerrado.
        """

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Indica si el observador se encuentra activo ydisponible para recibir eventos."""

    @abstractmethod
    def close(self) -> None:
        """Cierra los recursos asociados al observador."""


class SocketObserver(ClientObserver):
    """Implementación de ClientObserver sobre una conexión de socket TCP."""

    def __init__(self, client_socket: socket.socket, client_uuid: str) -> None:
        """Inicializa un observador de socket TCP.

        Args:
            client_socket: Socket TCP conectado al cliente observador.
            client_uuid: Identificador de CPU del cliente subscripto.
        """
        self._socket = client_socket
        self.client_uuid = client_uuid
        self._active = True
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        """Indica si el canal socket continúa operativo."""
        return self._active

    def update(self, event: Mapping[str, object]) -> bool:
        """Transmite la notificación en formato JSON delimitada por nueva línea.

        Args:
            event: Diccionario con la información del evento a emitir.

        Returns:
            True si la emisión fue exitosa; False si la conexión se interrumpió.
        """
        if not self._active:
            return False

        with self._lock:
            try:
                payload_str = json.dumps(event, ensure_ascii=False) + "\n"
                self._socket.sendall(payload_str.encode("utf-8"))
                LOGGER.debug(
                    "Notificación enviada al observer UUID [%s]",
                    self.client_uuid,
                )
            except OSError as exc:
                LOGGER.warning(
                    "Fallo al emitir evento al observer UUID [%s]: %s",
                    self.client_uuid,
                    exc,
                )
                self._active = False
                return False
            else:
                return True

    def close(self) -> None:
        """Cierra el socket TCP del cliente observador."""
        with self._lock:
            self._active = False
            try:
                self._socket.close()
            except OSError:
                LOGGER.debug("Socket ya cerrado o inaccesible")


class SubscriptionManager:
    """Sujeto del patrón Observer que administra los subscriptores activos."""

    def __init__(self) -> None:
        """Inicializa el administrador de subscripciones."""
        self._observers: list[ClientObserver] = []
        self._lock = threading.Lock()

    def subscribe(self, observer: ClientObserver) -> None:
        """Registra un nuevo observador en el gestor.

        Args:
            observer: Instancia de ClientObserver a registrar.
        """
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)
                LOGGER.info(
                    "Nuevo cliente subscripto. Total activos: %d",
                    len(self._observers),
                )

    def unsubscribe(self, observer: ClientObserver) -> None:
        """Elimina un observador del gestor.

        Args:
            observer: Instancia de ClientObserver a desuscribir.
        """
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)
                LOGGER.info(
                    "Cliente desuscripto. Total activos: %d",
                    len(self._observers),
                )

    def notify(self, event: Mapping[str, object]) -> int:
        """Difunde un evento corporativo a todos los observadores registrados.

        Elimina de forma segura aquellos observadores cuya conexión esté caída.

        Args:
            event: Carga útil del evento corporativo modificado.

        Returns:
            Cantidad de observadores notificados exitosamente.
        """
        with self._lock:
            active_observers: list[ClientObserver] = []
            successful_count = 0

            for observer in self._observers:
                if observer.is_active and observer.update(event):
                    active_observers.append(observer)
                    successful_count += 1
                else:
                    LOGGER.info(
                        "Descartando observador inactivo durante la notificación"
                    )
                    observer.close()

            self._observers = active_observers
            LOGGER.info(
                "Notificación distribuida a %d clientes subscriptos",
                successful_count,
            )
            return successful_count

    def get_observers_count(self) -> int:
        """Retorna la cantidad actual de observadores registrados.

        Returns:
            Número de subscriptores.
        """
        with self._lock:
            return len(self._observers)

    def clear(self) -> None:
        """Cierra y vacía todos los observadores."""
        with self._lock:
            for obs in self._observers:
                obs.close()
            self._observers.clear()
