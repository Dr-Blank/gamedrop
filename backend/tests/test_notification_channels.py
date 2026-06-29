"""Tests for channel protocol, DatabaseChannel, and notification routes/backfill."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.channels import DatabaseChannel, NotificationChannel, NtfyChannel
from app.channels.database import DatabaseChannel as _DBChannel
from app.models import (
    NotificationLog,
    PriceSnapshot,
    Product,
    Store,
    WatchlistItem,
)

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(session: Session) -> Store:
    s = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(s)
    session.commit()
    return s


@pytest.fixture()
def product(session: Session, store: Store) -> Product:
    p = Product(
        store_id="s1", external_id="e1", title="Catan", url="https://s1.com/catan"
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_ntfy_channel_implements_protocol():
    assert isinstance(NtfyChannel(), NotificationChannel)


def test_database_channel_implements_protocol():
    assert isinstance(DatabaseChannel(), NotificationChannel)


# ── DatabaseChannel.send writes a row ────────────────────────────────────────


def test_database_channel_writes_row(session: Session, product: Product):
    ch = _DBChannel()
    ch.send(
        kind="price_drop",
        title="Price drop: Catan",
        message="50 → 40 (20% off)\ns1",
        product_id=product.id,
        url="https://s1.com/catan",
        tags=[],
    )
    session.expire_all()
    rows = session.exec(select(NotificationLog)).all()
    assert len(rows) == 1
    assert rows[0].kind == "price_drop"
    assert rows[0].product_id == product.id
    assert rows[0].read_at is None


# ── NtfyChannel failure is isolated ──────────────────────────────────────────


def test_ntfy_channel_failure_does_not_raise():
    ch = NtfyChannel()
    with patch.object(ch, "_client") as mock_client_fn:
        mock_client_fn.return_value.send.side_effect = RuntimeError("ntfy down")
        # NtfyChannel.send itself may raise — _dispatch in notifier catches it.
        # Here we just verify the channel method doesn't swallow internally
        # (dispatcher is responsible for catching).
        with pytest.raises(RuntimeError):
            ch.send(
                kind="price_drop",
                title="X",
                message="Y",
                product_id=None,
                url=None,
                tags=[],
            )


# ── notifier._dispatch swallows channel failures ─────────────────────────────


def test_dispatch_continues_after_channel_failure():
    from app.notifier import _dispatch

    failing = MagicMock()
    failing.send.side_effect = RuntimeError("boom")
    succeeding = MagicMock()

    _dispatch(
        [failing, succeeding],
        kind="price_drop",
        title="T",
        message="M",
        product_id=None,
        url=None,
        tags=[],
    )
    succeeding.send.assert_called_once()


# ── GET /api/notifications ────────────────────────────────────────────────────


def test_list_notifications_empty(client: TestClient):
    r = client.get("/api/notifications")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["unread"] == 0


def test_list_notifications_returns_rows(
    client: TestClient, session: Session, product: Product
):
    session.add(
        NotificationLog(
            product_id=product.id,
            kind="price_drop",
            title="Price drop: Catan",
            message="50 → 40",
            product_url=product.url,
        )
    )
    session.commit()

    r = client.get("/api/notifications")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["unread"] == 1


# ── PATCH /api/notifications/{id}/read ───────────────────────────────────────


def test_mark_read(client: TestClient, session: Session, product: Product):
    row = NotificationLog(
        product_id=product.id,
        kind="back_in_stock",
        title="Back in stock: Catan",
        message="50 · s1",
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    r = client.patch(f"/api/notifications/{row.id}/read")
    assert r.status_code == 200
    assert r.json()["read_at"] is not None


def test_mark_read_404(client: TestClient):
    r = client.patch("/api/notifications/99999/read")
    assert r.status_code == 404


# ── POST /api/notifications/read-all ─────────────────────────────────────────


def test_mark_all_read(client: TestClient, session: Session, product: Product):
    for _ in range(3):
        session.add(
            NotificationLog(
                product_id=product.id,
                kind="price_drop",
                title="T",
                message="M",
            )
        )
    session.commit()

    r = client.post("/api/notifications/read-all")
    assert r.status_code == 200
    assert r.json()["marked"] == 3

    r2 = client.get("/api/notifications")
    assert r2.json()["unread"] == 0


# ── POST /api/notifications/backfill ─────────────────────────────────────────


def test_backfill_inserts_price_drop(
    client: TestClient, session: Session, product: Product
):
    item = WatchlistItem(product_id=product.id, active=True)
    session.add(item)
    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    session.add(PriceSnapshot(product_id=product.id, price=50.0, recorded_at=t0))
    session.add(PriceSnapshot(product_id=product.id, price=40.0, recorded_at=t1))
    session.commit()

    r = client.post("/api/notifications/backfill")
    assert r.status_code == 200
    assert r.json()["inserted"] >= 1

    rows = session.exec(
        select(NotificationLog).where(NotificationLog.kind == "price_drop")
    ).all()
    assert len(rows) >= 1


def test_backfill_is_idempotent(client: TestClient, session: Session, product: Product):
    item = WatchlistItem(product_id=product.id, active=True)
    session.add(item)
    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    session.add(PriceSnapshot(product_id=product.id, price=50.0, recorded_at=t0))
    session.add(PriceSnapshot(product_id=product.id, price=40.0, recorded_at=t1))
    session.commit()

    r1 = client.post("/api/notifications/backfill")
    r2 = client.post("/api/notifications/backfill")
    assert r1.json()["inserted"] == r2.json()["inserted"] == 0 or (
        r1.json()["inserted"] >= 1 and r2.json()["inserted"] == 0
    )


def test_backfill_skips_ntfy(client: TestClient, session: Session, product: Product):
    item = WatchlistItem(product_id=product.id, active=True)
    session.add(item)
    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    session.add(PriceSnapshot(product_id=product.id, price=50.0, recorded_at=t0))
    session.add(PriceSnapshot(product_id=product.id, price=40.0, recorded_at=t1))
    session.commit()

    with patch("app.channels.ntfy.NtfyChannel.send") as mock_ntfy:
        client.post("/api/notifications/backfill")
        mock_ntfy.assert_not_called()


# ── DatabaseChannel isolation: writes go to test DB not production ────────


def test_database_channel_writes_to_test_db_not_production(session: Session):
    """Regression: DatabaseChannel.send() must write to the in-memory test DB.
    Without patch_db_engine in conftest, _db.engine points to production and
    this test fails (row appears in prod, not in test session)."""
    ch = _DBChannel()
    ch.send(
        kind="price_increase",
        title="Price increased: Test",
        message="100 → 120 (+20%)\nstore",
        product_id=None,
        url=None,
        tags=[],
    )
    session.expire_all()
    rows = session.exec(select(NotificationLog)).all()
    assert len(rows) == 1, (
        "Row not in test DB — DatabaseChannel may be writing to production DB"
    )
