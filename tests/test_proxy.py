"""Unit tests for the Proxy pattern and corporate data service."""

from __future__ import annotations

from tests.test_observer import DummyObserver
from tp_final_integrador_is2.database import (
    CorporateDataRepository,
    CorporateLogRepository,
)
from tp_final_integrador_is2.observer import SubscriptionManager
from tp_final_integrador_is2.proxy import CorporateDataProxy, CorporateDataService


def test_corporate_data_service_create_new_record_fills_blanks() -> None:
    """Verify creating a new record populates non-provided fields with empty strings."""
    repo = CorporateDataRepository()
    repo.set_custom_table(None)
    service = CorporateDataService(repository=repo)

    result = service.set(
        client_uuid="UUID-1",
        record_id="UADER-NEW-01",
        fields={"ACTION": "set", "sede": "FCyT", "telefono": "03442 43-1442"},
    )
    assert result["id"] == "UADER-NEW-01"
    assert result["sede"] == "FCyT"
    assert result["telefono"] == "03442 43-1442"
    # Fields not informed must be blank strings ""
    assert result["cp"] == ""
    assert result["CUIT"] == ""
    assert result["domicilio"] == ""
    assert result["web"] == ""


def test_corporate_data_service_update_existing_preserves_unmentioned() -> None:
    """Verify updating existing record preserves existing fields not in payload."""
    repo = CorporateDataRepository()
    repo.set_custom_table(None)
    service = CorporateDataService(repository=repo)

    service.set(
        client_uuid="UUID-1",
        record_id="UADER-EXIST",
        fields={"sede": "FCyT", "telefono": "111111", "localidad": "CdU"},
    )

    # Partial update: only update 'telefono'
    updated = service.set(
        client_uuid="UUID-1",
        record_id="UADER-EXIST",
        fields={"telefono": "999999"},
    )
    assert updated["sede"] == "FCyT"
    assert updated["localidad"] == "CdU"
    assert updated["telefono"] == "999999"


def test_corporate_data_proxy_generates_audit_log_and_notifies() -> None:
    """Verify CorporateDataProxy records audit entries.

    in CorporateLog and notifies observers.
    """
    data_repo = CorporateDataRepository()
    data_repo.set_custom_table(None)

    log_repo = CorporateLogRepository()
    log_repo.set_custom_table(None)

    sub_manager = SubscriptionManager()
    observer = DummyObserver()
    sub_manager.subscribe(observer)

    proxy = CorporateDataProxy(
        real_service=CorporateDataService(repository=data_repo),
        log_repository=log_repo,
        subscription_manager=sub_manager,
    )

    # 1. Test SET
    updated = proxy.set(
        client_uuid="CLIENT-CPU-1",
        record_id="UADER-PROXY-01",
        fields={"sede": "Central", "cp": "3260"},
    )
    assert updated["id"] == "UADER-PROXY-01"
    assert updated["sede"] == "Central"

    # Verify notification reached observer
    assert len(observer.events) == 1
    assert observer.events[0]["id"] == "UADER-PROXY-01"

    # Verify audit log in CorporateLog
    logs = log_repo.get_logs()
    set_logs = [entry for entry in logs if entry.get("action") == "set"]
    assert len(set_logs) >= 1
    assert set_logs[-1]["CPUid"] == "CLIENT-CPU-1"
    assert set_logs[-1]["requested_id"] == "UADER-PROXY-01"

    # 2. Test GET
    retrieved = proxy.get("CLIENT-CPU-1", "UADER-PROXY-01")
    assert retrieved is not None
    assert retrieved["sede"] == "Central"
    logs = log_repo.get_logs()
    get_logs = [entry for entry in logs if entry.get("action") == "get"]
    assert len(get_logs) >= 1

    # 3. Test LIST
    all_records = proxy.list("CLIENT-CPU-1")
    assert len(all_records) >= 1
    logs = log_repo.get_logs()
    list_logs = [entry for entry in logs if entry.get("action") == "list"]
    assert len(list_logs) >= 1

    # 4. Test SUBSCRIBE registration
    new_obs = DummyObserver()
    proxy.register_subscription("CLIENT-CPU-2", new_obs)
    assert sub_manager.get_observers_count() == 2
    logs = log_repo.get_logs()
    sub_logs = [entry for entry in logs if entry.get("action") == "subscribe"]
    assert len(sub_logs) >= 1
