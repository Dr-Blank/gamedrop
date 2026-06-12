"""Feeds + global search + home dashboard."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, Product, Store, WatchlistItem


def _seed(session: Session):
    session.add(
        Store(id="s1", name="Store One", type="shopify", base_url="https://s1.com")
    )
    session.commit()

    products = [
        Product(store_id="s1", external_id="e1", title="Catan"),
        Product(store_id="s1", external_id="e2", title="Pandemic"),
        Product(store_id="s1", external_id="e3", title="Azul"),
    ]
    for p in products:
        session.add(p)
    session.commit()
    for p in products:
        session.refresh(p)

    base = datetime(2026, 1, 1)

    # Catan: price dropped 30 -> 20 (a drop)
    session.add(
        PriceSnapshot(
            product_id=products[0].id, price=30.0, available=True, recorded_at=base
        )
    )
    session.add(
        PriceSnapshot(
            product_id=products[0].id,
            price=20.0,
            available=True,
            recorded_at=base + timedelta(days=1),
        )
    )
    # Pandemic: price rose 40 -> 50 (not a drop)
    session.add(
        PriceSnapshot(
            product_id=products[1].id, price=40.0, available=True, recorded_at=base
        )
    )
    session.add(
        PriceSnapshot(
            product_id=products[1].id,
            price=50.0,
            available=True,
            recorded_at=base + timedelta(days=1),
        )
    )
    # Azul: discounted via compare_at, single snapshot, newest first-seen
    session.add(
        PriceSnapshot(
            product_id=products[2].id,
            price=25.0,
            compare_at_price=50.0,
            available=True,
            recorded_at=base + timedelta(days=5),
        )
    )
    session.commit()
    return products


def test_feed_drops_only_includes_price_drops(client: TestClient, session: Session):
    _seed(session)
    items = client.get("/api/feed/drops").json()["items"]
    titles = [i["product"]["title"] for i in items]
    assert "Catan" in titles
    assert "Pandemic" not in titles  # price rose
    catan = next(i for i in items if i["product"]["title"] == "Catan")
    assert catan["previous_price"] == 30.0
    assert catan["latest_price"]["price"] == 20.0


def test_feed_new_orders_by_first_seen(client: TestClient, session: Session):
    _seed(session)
    items = client.get("/api/feed/new").json()["items"]
    # Azul was first seen last → should lead.
    assert items[0]["product"]["title"] == "Azul"


def test_feed_discounts_only_positive(client: TestClient, session: Session):
    _seed(session)
    items = client.get("/api/feed/discounts").json()["items"]
    titles = [i["product"]["title"] for i in items]
    assert titles == ["Azul"]
    assert items[0]["discount_pct"] == 50.0


def test_search_matches_title(client: TestClient, session: Session):
    _seed(session)
    items = client.get("/api/search?q=cat").json()["items"]
    assert [i["product"]["title"] for i in items] == ["Catan"]


def test_search_blank_returns_empty(client: TestClient, session: Session):
    _seed(session)
    assert client.get("/api/search?q=").json()["items"] == []


def test_home_has_all_shelves(client: TestClient, session: Session):
    products = _seed(session)
    session.add(WatchlistItem(product_id=products[0].id))
    session.commit()

    data = client.get("/api/home").json()
    assert set(data) == {"watchlist", "price_drops", "new_additions", "top_discounts"}
    assert data["watchlist"][0]["product"]["title"] == "Catan"
    assert data["watchlist"][0]["watchlist"]["active"] is True
    assert any(i["product"]["title"] == "Catan" for i in data["price_drops"])
