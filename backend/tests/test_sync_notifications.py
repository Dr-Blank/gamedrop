"""End-to-end sync → NotificationLog tests.

Regression: notifications never appeared after a store sync; they only showed up
after manually hitting the backfill ("load history") endpoint.

Root cause: DatabaseChannel opens its own Session on app.db.engine, but the
scraper called it from *inside* its still-open write transaction. On a
file-backed SQLite database only one writer is allowed, so the channel's INSERT
raised "database is locked". _dispatch swallows channel exceptions, so the
notification was dropped silently.

These tests deliberately use a file-backed engine — the shared in-memory
StaticPool engine from conftest uses a single connection and therefore cannot
reproduce the lock.
"""

import asyncio
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.channels import DatabaseChannel
from app.models import (
    NotificationLog,
    PriceSnapshot,
    Product,
    Store,
    WatchlistItem,
)
from app.scraper import sync_store


@pytest.fixture(name="file_engine")
def file_engine_fixture(tmp_path, patch_db_engine):
    """A real on-disk SQLite engine wired into app.db / app.config.

    Depends on patch_db_engine purely for ordering: the autouse fixture points
    the app at the in-memory engine, and we need to win afterwards.
    """
    from app import config as _config
    from app import db as _db

    engine = create_engine(
        f"sqlite:///{tmp_path}/tracker.db", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    _db.engine = engine
    _config.engine = engine
    yield engine
    engine.dispose()


def _payload(price: float, available: bool = True) -> list[dict]:
    return [
        {
            "external_id": "e1",
            "title": "Catan",
            "handle": "catan",
            "url": "https://s1.com/products/catan",
            "image_url": None,
            "variants": [
                {
                    "variant_id": "v1",
                    "variant_title": "Default",
                    "price": price,
                    "compare_at_price": None,
                    "available": available,
                }
            ],
        }
    ]


class _FakeAdapter:
    def __init__(self, payload: list[dict]):
        self.payload = payload

    async def fetch_products(self) -> list[dict]:
        return self.payload


def _run_sync(engine, payload: list[dict]) -> dict:
    """Sync store s1 with a canned payload, DatabaseChannel only (no ntfy)."""
    with Session(engine) as session:
        store = session.get(Store, "s1")
        with (
            patch("app.scraper.get_adapter", return_value=_FakeAdapter(payload)),
            patch("app.notifier._channels", return_value=[DatabaseChannel()]),
        ):
            return asyncio.run(sync_store(store))


@pytest.fixture(name="watched_store")
def watched_store_fixture(file_engine):
    """Store s1, synced once at 500.0, with the resulting product watchlisted."""
    with Session(file_engine) as session:
        session.add(
            Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
        )
        session.commit()

    _run_sync(file_engine, _payload(500.0))

    with Session(file_engine) as session:
        product = session.exec(select(Product)).one()
        session.add(WatchlistItem(product_id=product.id, active=True))
        session.commit()
    return file_engine


def test_sync_price_drop_writes_notification_log(watched_store):
    """A price drop seen during a sync must land in NotificationLog immediately,
    without needing the backfill endpoint."""
    _run_sync(watched_store, _payload(400.0))

    with Session(watched_store) as session:
        logs = session.exec(select(NotificationLog)).all()

    assert [log.kind for log in logs] == ["price_drop"]
    assert logs[0].title == "Price drop: Catan"
    assert logs[0].product_url == "https://s1.com/products/catan"


def test_sync_back_in_stock_writes_notification_log(watched_store):
    _run_sync(watched_store, _payload(500.0, available=False))
    _run_sync(watched_store, _payload(500.0, available=True))

    with Session(watched_store) as session:
        kinds = [log.kind for log in session.exec(select(NotificationLog)).all()]

    assert kinds == ["out_of_stock", "back_in_stock"]


def test_sync_notification_sent_at_matches_snapshot(watched_store):
    """sent_at must equal the snapshot's recorded_at so the backfill dedup key
    (product_id, kind, sent_at) still matches and does not double-insert."""
    _run_sync(watched_store, _payload(400.0))

    with Session(watched_store) as session:
        log = session.exec(select(NotificationLog)).one()
        snap = session.exec(
            select(PriceSnapshot).where(PriceSnapshot.price == 400.0)
        ).one()

    assert log.sent_at == snap.recorded_at


def test_sync_notification_dispatch_survives_channel_failure(watched_store):
    """A channel blowing up must not abort the sync or lose the sync result."""
    boom = DatabaseChannel()
    with (
        patch.object(DatabaseChannel, "send", side_effect=RuntimeError("channel down")),
        patch("app.scraper.get_adapter", return_value=_FakeAdapter(_payload(400.0))),
        patch("app.notifier._channels", return_value=[boom]),
        Session(watched_store) as session,
    ):
        store = session.get(Store, "s1")
        result = asyncio.run(sync_store(store))

    assert result["price_changes"] == 1
    with Session(watched_store) as session:
        assert session.get(Store, "s1").last_sync_error is None
