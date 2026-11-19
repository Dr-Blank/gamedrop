"""Shopify listings fetched by the browser are recorded like a sync."""

import json
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.adapters.throttle import RATE_LIMITED_PREFIX
from app.models import PriceSnapshot, Product, Store, SyncLog
from app.scraper import SCHEDULE_JITTER, due_stores
from tests.factories import make_store


def _entry(pid: int, price: str = "100.00", available: bool = True) -> dict:
    return {
        "id": pid,
        "title": f"Game {pid}",
        "handle": f"game-{pid}",
        "images": [{"src": f"https://img/{pid}.png"}],
        "variants": [
            {"id": pid * 10, "title": "Default", "price": price, "available": available}
        ],
    }


def _import(client, products, store_id="s1"):
    return client.post(f"/api/stores/{store_id}/import", json={"products": products})


def test_import_adds_listings_and_marks_the_store_synced(client, session: Session):
    make_store(session, last_sync_error="rate limited by shop, next try in 1h")

    r = _import(client, [_entry(1), _entry(2)])

    assert r.status_code == 200
    assert r.json()["new_products"] == 2
    products = session.exec(select(Product).order_by(Product.external_id)).all()
    assert [p.url for p in products] == [
        "https://s1.com/products/game-1",
        "https://s1.com/products/game-2",
    ]
    store = session.get(Store, "s1")
    session.refresh(store)
    assert store.last_sync_error is None
    assert store.last_synced_at is not None
    log = session.exec(select(SyncLog)).one()
    assert log.error is None and log.new_products == 2


def test_import_records_price_changes_against_earlier_readings(
    client, session: Session
):
    make_store(session)
    _import(client, [_entry(1, "100.00")])

    r = _import(client, [_entry(1, "80.00")])

    assert r.json()["price_changes"] == 1
    prices = session.exec(
        select(PriceSnapshot.price).order_by(PriceSnapshot.recorded_at)
    ).all()
    assert prices == [100.0, 80.0]


def test_import_counts_a_listing_seen_on_two_pages_once(client, session: Session):
    make_store(session)

    r = _import(client, [_entry(1), _entry(1)])

    assert r.json()["new_products"] == 1


def test_import_is_shopify_only(client, session: Session):
    make_store(session, type="woocommerce")

    assert _import(client, [_entry(1)]).status_code == 400


def test_import_rejects_entries_that_are_not_shopify_products(client, session: Session):
    make_store(session)

    assert _import(client, [{"title": "no id"}]).status_code == 422
    assert _import(client, [{"id": 1, "variants": []}]).status_code == 422
    assert session.exec(select(SyncLog)).all() == []


def test_import_with_nothing_to_record_is_refused(client, session: Session):
    make_store(session)

    assert _import(client, []).status_code == 422


def test_an_import_puts_off_the_next_scheduled_sync(client, session: Session):
    rate_limited = f"{RATE_LIMITED_PREFIX}, next try in 1h"
    make_store(session, scrape_config=json.dumps({"sync_interval_hours": 24}))
    long_ago = datetime.utcnow() - timedelta(days=30)
    session.add(SyncLog(store_id="s1", started_at=long_ago, error=rate_limited))
    session.commit()
    assert [s.id for s in due_stores(datetime.utcnow())] == ["s1"]

    _import(client, [_entry(1)])

    now = datetime.utcnow()
    longest_wait = timedelta(hours=24) * (1 + SCHEDULE_JITTER)
    assert due_stores(now + timedelta(hours=20)) == []
    assert [s.id for s in due_stores(now + longest_wait)] == ["s1"]


def test_import_to_an_unknown_store_is_not_found(client):
    assert _import(client, [_entry(1)], store_id="nope").status_code == 404
