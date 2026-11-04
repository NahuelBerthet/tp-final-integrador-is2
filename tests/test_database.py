"""Unit tests for database repositories implementing the Singleton pattern."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from tp_final_integrador_is2.database import (
    CorporateDataRepository,
    CorporateLogRepository,
    get_corporate_data_repository,
    get_corporate_log_repository,
)


def test_corporate_data_repository_is_singleton() -> None:
    """Verify CorporateDataRepository implements the Singleton pattern."""
    repo1 = CorporateDataRepository()
    repo2 = CorporateDataRepository()
    repo3 = get_corporate_data_repository()
    assert repo1 is repo2
    assert repo2 is repo3


def test_corporate_log_repository_is_singleton() -> None:
    """Verify CorporateLogRepository implements the Singleton pattern."""
    repo1 = CorporateLogRepository()
    repo2 = CorporateLogRepository()
    repo3 = get_corporate_log_repository()
    assert repo1 is repo2
    assert repo2 is repo3


def test_corporate_data_repository_multithreaded_singleton() -> None:
    """Verify thread-safety of CorporateDataRepository Singleton instantiation."""
    instances: list[CorporateDataRepository] = []

    def instantiate() -> None:
        instances.append(CorporateDataRepository())

    threads = [threading.Thread(target=instantiate) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    first = instances[0]
    for instance in instances[1:]:
        assert instance is first


def test_corporate_data_repository_memory_crud() -> None:
    """Verify put, get, and list operations in local memory fallback."""
    repo = CorporateDataRepository()
    repo.set_custom_table(None)

    # Put new item
    item = {"id": "REC-01", "sede": "FCyT", "telefono": "123456"}
    saved = repo.put_record(item)
    assert saved["id"] == "REC-01"
    assert saved["sede"] == "FCyT"

    # Get item
    retrieved = repo.get_record("REC-01")
    assert retrieved is not None
    assert retrieved["sede"] == "FCyT"

    # Get non-existing item
    assert repo.get_record("NON-EXISTENT") is None

    # List items
    all_items = repo.list_records()
    assert any(i["id"] == "REC-01" for i in all_items)


def test_corporate_data_repository_put_missing_id() -> None:
    """Verify put_record raises ValueError if record has no ID."""
    repo = CorporateDataRepository()
    with pytest.raises(ValueError, match="debe contener el campo 'id'"):
        repo.put_record({"sede": "FCyT"})


def test_corporate_data_repository_with_mock_table() -> None:
    """Verify DynamoDB table calls and ClientError handling."""
    repo = CorporateDataRepository()
    mock_table = MagicMock()
    repo.set_custom_table(mock_table)

    # Get item
    mock_table.get_item.return_value = {
        "Item": {"id": "REC-02", "web": "http://uader.edu.ar"}
    }
    rec = repo.get_record("REC-02")
    assert rec is not None
    assert rec["web"] == "http://uader.edu.ar"

    # Put item
    repo.put_record({"id": "REC-02", "web": "http://uader.edu.ar"})
    mock_table.put_item.assert_called_once()

    # List items
    mock_table.scan.return_value = {"Items": [{"id": "REC-02"}]}
    items = repo.list_records()
    assert len(items) == 1

    # ClientError handling on get
    mock_table.get_item.side_effect = ClientError(
        {"Error": {"Message": "Fail"}}, "GetItem"
    )
    with pytest.raises(RuntimeError, match="Fallo al consultar registro"):
        repo.get_record("REC-02")

    # ClientError handling on put
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Message": "Fail"}}, "PutItem"
    )
    with pytest.raises(RuntimeError, match="Fallo al escribir en CorporateData"):
        repo.put_record({"id": "REC-02"})

    # ClientError handling on scan
    mock_table.scan.side_effect = ClientError({"Error": {"Message": "Fail"}}, "Scan")
    with pytest.raises(RuntimeError, match="Fallo al listar registros"):
        repo.list_records()

    # Restore fallback
    repo.set_custom_table(None)


def test_corporate_log_repository_crud_and_mock() -> None:
    """Verify CorporateLogRepository logging in memory and with mock table."""
    repo = CorporateLogRepository()
    repo.set_custom_table(None)

    # Log entry in memory
    entry = repo.log_entry(
        client_uuid="UUID-123",
        session_id="SESS-456",
        action="get",
        requested_id="REC-99",
    )
    assert entry["CPUid"] == "UUID-123"
    assert entry["action"] == "get"
    assert entry["requested_id"] == "REC-99"

    logs = repo.get_logs()
    assert any(log["sessionid"] == "SESS-456" for log in logs)

    # Mock table
    mock_table = MagicMock()
    repo.set_custom_table(mock_table)
    repo.log_entry("UUID-123", "SESS-789", "list")
    mock_table.put_item.assert_called_once()

    # ClientError handling
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Message": "Fail"}}, "PutItem"
    )
    with pytest.raises(RuntimeError, match="Fallo al registrar entrada"):
        repo.log_entry("UUID-123", "SESS-789", "list")

    # Restore fallback
    repo.set_custom_table(None)
