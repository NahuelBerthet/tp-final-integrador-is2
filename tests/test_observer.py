"""Unit tests for the Observer pattern implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from tp_final_integrador_is2.observer import (
    ClientObserver,
    SocketObserver,
    SubscriptionManager,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class DummyObserver(ClientObserver):
    """Observer de prueba en memoria."""

    def __init__(self) -> None:
        """Inicializa el observer con una lista de eventos vacía."""
        self.events: list[dict[str, object]] = []
        self._active = True

    def update(self, event: Mapping[str, object]) -> bool:
        """Simula la recepción de un evento."""
        if not self._active:
            return False
        self.events.append(dict(event))
        return True

    @property
    def is_active(self) -> bool:
        """Indica si el observer de prueba está activo."""
        return self._active

    def close(self) -> None:
        """Cierra el observer de prueba."""
        self._active = False


def test_subscription_manager_subscribe_and_unsubscribe() -> None:
    """Verify subscribe and unsubscribe methods in SubscriptionManager."""
    manager = SubscriptionManager()
    obs1 = DummyObserver()
    obs2 = DummyObserver()

    manager.subscribe(obs1)
    manager.subscribe(obs2)
    # Duplicate subscription ignored
    manager.subscribe(obs1)
    assert manager.get_observers_count() == 2

    manager.unsubscribe(obs1)
    assert manager.get_observers_count() == 1
    # Unsubscribe nonexistent observer does not fail
    manager.unsubscribe(obs1)
    assert manager.get_observers_count() == 1


def test_subscription_manager_notify() -> None:
    """Verify notify delivers events to all registered observers."""
    manager = SubscriptionManager()
    obs1 = DummyObserver()
    obs2 = DummyObserver()
    manager.subscribe(obs1)
    manager.subscribe(obs2)

    event = {"id": "REC-01", "action": "set", "status": "updated"}
    count = manager.notify(event)
    assert count == 2
    assert len(obs1.events) == 1
    assert obs1.events[0]["status"] == "updated"
    assert len(obs2.events) == 1


def test_subscription_manager_removes_inactive_observers_on_notify() -> None:
    """Verify broken observers are automatically discarded during notify."""
    manager = SubscriptionManager()
    obs_active = DummyObserver()
    obs_broken = DummyObserver()
    obs_broken.close()

    manager.subscribe(obs_active)
    manager.subscribe(obs_broken)
    assert manager.get_observers_count() == 2

    count = manager.notify({"change": True})
    assert count == 1
    assert manager.get_observers_count() == 1


def test_subscription_manager_clear() -> None:
    """Verify clear closes all observers and empties the registry."""
    manager = SubscriptionManager()
    obs1 = DummyObserver()
    obs2 = DummyObserver()
    manager.subscribe(obs1)
    manager.subscribe(obs2)

    manager.clear()
    assert manager.get_observers_count() == 0
    assert obs1.is_active is False
    assert obs2.is_active is False


def test_socket_observer_send_success() -> None:
    """Verify SocketObserver encodes and transmits events."""
    mock_socket = MagicMock()
    observer = SocketObserver(mock_socket, "UUID-999")
    assert observer.is_active is True

    success = observer.update({"id": "REC-01", "sede": "FCyT"})
    assert success is True
    mock_socket.sendall.assert_called_once()
    payload = mock_socket.sendall.call_args[0][0].decode("utf-8")
    assert '"id": "REC-01"' in payload
    assert payload.endswith("\n")


def test_socket_observer_handles_oserror() -> None:
    """Verify SocketObserver marks itself inactive on socket send error."""
    mock_socket = MagicMock()
    mock_socket.sendall.side_effect = OSError("Broken pipe")
    observer = SocketObserver(mock_socket, "UUID-999")

    success = observer.update({"data": 123})
    assert success is False
    assert observer.is_active is False

    # Second call while inactive returns False immediately
    assert observer.update({"data": 456}) is False


def test_socket_observer_close() -> None:
    """Verify close shuts down socket and sets active to False."""
    mock_socket = MagicMock()
    observer = SocketObserver(mock_socket, "UUID-999")
    observer.close()
    assert observer.is_active is False
    mock_socket.close.assert_called_once()
