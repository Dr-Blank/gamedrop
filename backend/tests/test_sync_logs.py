"""Tests for SyncLog, GET /stores/{id}/logs, and last_synced_at / last_sync_error on Store."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Store, SyncLog


def _store(session: Session, sid: str = "s1") -> Store:
    s = Store(id=sid, name=sid, type="shopify", base_url=f"https://{sid}.com")
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


def _log(session: Session, store_id: str, **kwargs) -> SyncLog:
    log = SyncLog(
        store_id=store_id,
        started_at=kwargs.get("started_at", datetime.utcnow()),
        finished_at=kwargs.get("finished_at", datetime.utcnow()),
        new_products=kwargs.get("new_products", 0),
        price_changes=kwargs.get("price_changes", 0),
        error=kwargs.get("error"),
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def test_get_sync_logs_empty(client: TestClient, session: Session):
    _store(session)
    r = client.get("/api/stores/s1/logs")
    assert r.status_code == 200
    assert r.json() == []


def test_get_sync_logs_returns_entries(client: TestClient, session: Session):
    _store(session)
    _log(session, "s1", new_products=5, price_changes=2)
    _log(session, "s1", error="fetch failed: timeout")

    r = client.get("/api/stores/s1/logs")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


def test_get_sync_logs_newest_first(client: TestClient, session: Session):
    _store(session)
    _log(session, "s1", started_at=datetime(2025, 1, 1), new_products=1)
    _log(session, "s1", started_at=datetime(2025, 6, 1), new_products=99)

    r = client.get("/api/stores/s1/logs")
    assert r.status_code == 200
    data = r.json()
    assert data[0]["new_products"] == 99  # most recent first


def test_get_sync_logs_limit(client: TestClient, session: Session):
    _store(session)
    for i in range(5):
        _log(session, "s1", new_products=i)

    r = client.get("/api/stores/s1/logs?limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_get_sync_logs_store_not_found(client: TestClient):
    r = client.get("/api/stores/ghost/logs")
    assert r.status_code == 404


def test_get_sync_logs_isolates_by_store(client: TestClient, session: Session):
    _store(session, "s1")
    _store(session, "s2")
    _log(session, "s1", new_products=10)
    _log(session, "s2", new_products=99)

    r = client.get("/api/stores/s1/logs")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["new_products"] == 10


def test_sync_log_error_field(client: TestClient, session: Session):
    _store(session)
    _log(session, "s1", error="fetch failed: connection refused")

    r = client.get("/api/stores/s1/logs")
    data = r.json()
    assert data[0]["error"] == "fetch failed: connection refused"


def test_store_last_synced_at_and_error_fields(client: TestClient, session: Session):
    """Store model exposes last_synced_at and last_sync_error via list endpoint."""
    s = _store(session)
    assert s.last_synced_at is None
    assert s.last_sync_error is None

    now = datetime.utcnow()
    s.last_synced_at = now
    s.last_sync_error = "oops"
    session.add(s)
    session.commit()

    r = client.get("/api/stores/")
    assert r.status_code == 200
    store_data = r.json()[0]
    assert store_data["last_sync_error"] == "oops"
    assert store_data["last_synced_at"] is not None
