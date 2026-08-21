import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, Product, Store

from .factories import make_product

BASE = datetime(2026, 6, 1)


def _seed(session: Session, prices, store_id="s1", title="Catan", product=None):
    """A listing with one snapshot per (price, day-offset) pair, oldest first."""
    if product is None:
        if not session.get(Store, store_id):
            session.add(
                Store(
                    id=store_id,
                    name=store_id.upper(),
                    type="shopify",
                    base_url=f"https://{store_id}.com",
                )
            )
            session.commit()
        product = make_product(session, store_id=store_id, title=title)
    for offset, price in enumerate(prices):
        session.add(
            PriceSnapshot(
                product_id=product.id,
                price=price,
                recorded_at=BASE + timedelta(days=offset),
            )
        )
    session.commit()
    return product


def _snapshots(session: Session, product_id: int) -> list[PriceSnapshot]:
    from sqlmodel import select

    return list(
        session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id)
            .order_by(PriceSnapshot.recorded_at)
        )
    )


def _cond(field, op, value):
    return {"type": "condition", "field": field, "op": op, "value": value}


# ---------------------------------------------------------------------------
# Toggling
# ---------------------------------------------------------------------------


def test_ignore_marks_the_snapshot(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]

    r = client.put(f"/api/prices/snapshot/{snap.id}/ignore")
    assert r.status_code == 200
    assert r.json()["ignored"] is True


def test_restore_clears_the_flag(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    r = client.delete(f"/api/prices/snapshot/{snap.id}/ignore")
    assert r.status_code == 200
    assert r.json()["ignored"] is False


def test_ignore_unknown_snapshot_404s(client: TestClient):
    assert client.put("/api/prices/snapshot/999/ignore").status_code == 404


def test_ignoring_keeps_the_row(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    assert len(_snapshots(session, product.id)) == 2


# ---------------------------------------------------------------------------
# History reads
# ---------------------------------------------------------------------------


def test_price_history_drops_ignored(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    data = client.get(f"/api/prices/product/{product.id}").json()
    assert [h["price"] for h in data["history"]] == [2699.0]
    assert [h["price"] for h in data["ignored"]] == [899.0]


def test_price_history_falls_back_when_all_ignored(
    client: TestClient, session: Session
):
    product = _seed(session, [899.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    data = client.get(f"/api/prices/product/{product.id}").json()
    assert [h["price"] for h in data["history"]] == [899.0]
    assert data["ignored"] == []


def test_game_series_drops_ignored(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    data = client.get(f"/api/games/{product.game_id}").json()
    series = data["series"][0]
    assert [h["price"] for h in series["history"]] == [2699.0]
    assert [h["price"] for h in series["ignored"]] == [899.0]


def test_game_series_falls_back_when_all_ignored(client: TestClient, session: Session):
    product = _seed(session, [899.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    series = client.get(f"/api/games/{product.game_id}").json()["series"][0]
    assert [h["price"] for h in series["history"]] == [899.0]
    assert series["ignored"] == []


def test_listing_detail_drops_ignored(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    snap = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{snap.id}/ignore")

    data = client.get(f"/api/games/{product.game_id}/listing/{product.id}").json()
    assert [h["price"] for h in data["history"]] == [2699.0]
    assert [h["price"] for h in data["ignored"]] == [899.0]


# ---------------------------------------------------------------------------
# Latest price, filters and sorts
# ---------------------------------------------------------------------------


def test_ignored_latest_falls_back_to_the_one_before(
    client: TestClient, session: Session
):
    product = _seed(session, [2699.0, 99999.0])
    bogus = _snapshots(session, product.id)[-1]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    items = client.post("/api/browse/query", json={}).json()["items"]
    assert items[0]["latest_price"]["price"] == 2699.0


def test_ignored_price_is_not_filterable(client: TestClient, session: Session):
    product = _seed(session, [2699.0, 99999.0])
    bogus = _snapshots(session, product.id)[-1]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    r = client.post("/api/browse/query", json={"filters": _cond("price", "gte", 90000)})
    assert r.json()["items"] == []


def test_ignored_price_is_not_sorted_on(client: TestClient, session: Session):
    cheap = _seed(session, [500.0], title="Azul")
    _seed(session, [2699.0, 99999.0], title="Catan")

    body = {"sorts": [{"field": "price", "dir": "desc"}]}
    before = client.post("/api/browse/query", json=body).json()["items"]
    assert before[0]["product"]["title"] == "Catan"

    bogus = _snapshots(session, before[0]["product"]["id"])[-1]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    after = client.post("/api/browse/query", json=body).json()["items"]
    assert after[0]["latest_price"]["price"] == 2699.0
    assert after[-1]["product"]["id"] == cheap.id


def test_price_change_ignores_the_bogus_reading(client: TestClient, session: Session):
    product = _seed(session, [2500.0, 899.0, 2699.0])
    bogus = _snapshots(session, product.id)[1]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    # Without the 899 the previous reading is 2500, so the move is +199.
    r = client.post(
        "/api/browse/query", json={"filters": _cond("price_change", "gte", 190)}
    )
    assert [i["product"]["id"] for i in r.json()["items"]] == [product.id]


def test_first_seen_ignores_the_bogus_reading(client: TestClient, session: Session):
    old = _seed(session, [], title="Catan")
    session.add(PriceSnapshot(product_id=old.id, price=899.0, recorded_at=BASE))
    session.add(
        PriceSnapshot(
            product_id=old.id, price=2699.0, recorded_at=BASE + timedelta(days=10)
        )
    )
    recent = _seed(session, [], title="Azul")
    session.add(
        PriceSnapshot(
            product_id=recent.id, price=1500.0, recorded_at=BASE + timedelta(days=5)
        )
    )
    session.commit()

    body = {"sorts": [{"field": "first_seen", "dir": "desc"}]}
    before = client.post("/api/browse/query", json=body).json()["items"]
    assert [i["product"]["id"] for i in before] == [recent.id, old.id]

    bogus = _snapshots(session, old.id)[0]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    after = client.post("/api/browse/query", json=body).json()["items"]
    assert [i["product"]["id"] for i in after] == [old.id, recent.id]


def test_ignored_is_not_a_filter_field(client: TestClient):
    names = {f["name"] for f in client.get("/api/browse/fields").json()}
    assert "ignored" not in names


def test_card_price_history_drops_ignored(client: TestClient, session: Session):
    product = _seed(session, [899.0, 2699.0])
    bogus = _snapshots(session, product.id)[0]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    items = client.post("/api/browse/query", json={}).json()["items"]
    assert [h["price"] for h in items[0]["price_history"]] == [2699.0]


def test_search_latest_price_ignores_bogus(client: TestClient, session: Session):
    product = _seed(session, [2699.0, 99999.0])
    bogus = _snapshots(session, product.id)[-1]
    client.put(f"/api/prices/snapshot/{bogus.id}/ignore")

    results = client.get("/api/prices/search?q=catan").json()
    assert results[0]["latest_price"]["price"] == 2699.0
    assert product.id == results[0]["product"]["id"]


# ---------------------------------------------------------------------------
# Manual entry
# ---------------------------------------------------------------------------


def test_manual_snapshot_is_recorded(client: TestClient, session: Session):
    product = _seed(session, [2699.0])

    r = client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": 1499.0, "recorded_at": "2025-01-15T00:00:00"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["price"] == 1499.0
    assert body["source"] == "manual"
    assert body["recorded_at"].startswith("2025-01-15")


def test_scraped_snapshot_is_marked_as_such(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    assert _snapshots(session, product.id)[0].source == "scrape"


def test_manual_snapshot_joins_the_history(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": 1499.0, "recorded_at": "2025-01-15T00:00:00"},
    )

    series = client.get(f"/api/games/{product.game_id}").json()["series"][0]
    assert [h["price"] for h in series["history"]] == [1499.0, 2699.0]
    assert [h["source"] for h in series["history"]] == ["manual", "scrape"]


def test_manual_snapshot_backdated_does_not_become_latest(
    client: TestClient, session: Session
):
    product = _seed(session, [2699.0])
    client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": 1499.0, "recorded_at": "2025-01-15T00:00:00"},
    )

    items = client.post("/api/browse/query", json={}).json()["items"]
    assert items[0]["latest_price"]["price"] == 2699.0


def test_manual_snapshot_rejects_negative_price(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    r = client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": -1, "recorded_at": "2025-01-15T00:00:00"},
    )
    assert r.status_code == 400


def test_manual_snapshot_unknown_product_404s(client: TestClient):
    r = client.post(
        "/api/prices/product/999/snapshot",
        json={"price": 10.0, "recorded_at": "2025-01-15T00:00:00"},
    )
    assert r.status_code == 404


def test_manual_snapshot_can_be_deleted(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    created = client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": 1499.0, "recorded_at": "2025-01-15T00:00:00"},
    ).json()

    assert client.delete(f"/api/prices/snapshot/{created['id']}").status_code == 200
    assert len(_snapshots(session, product.id)) == 1


def test_scraped_snapshot_cannot_be_deleted(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    snap = _snapshots(session, product.id)[0]

    assert client.delete(f"/api/prices/snapshot/{snap.id}").status_code == 400
    assert len(_snapshots(session, product.id)) == 1


def test_manual_snapshot_can_be_ignored(client: TestClient, session: Session):
    product = _seed(session, [2699.0])
    created = client.post(
        f"/api/prices/product/{product.id}/snapshot",
        json={"price": 1.0, "recorded_at": "2025-01-15T00:00:00"},
    ).json()
    client.put(f"/api/prices/snapshot/{created['id']}/ignore")

    series = client.get(f"/api/games/{product.game_id}").json()["series"][0]
    assert [h["price"] for h in series["history"]] == [2699.0]


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class _FakeAdapter:
    def __init__(self, price: float):
        self.price = price

    async def fetch_products(self) -> list[dict]:
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
                        "price": self.price,
                        "compare_at_price": None,
                        "available": True,
                    }
                ],
            }
        ]


def _sync(session: Session, price: float) -> None:
    from app.scraper import sync_store

    store = session.get(Store, "s1")
    with patch("app.scraper.get_adapter", return_value=_FakeAdapter(price)):
        asyncio.run(sync_store(store))


@pytest.fixture(name="synced_product")
def synced_product_fixture(session: Session):
    """Store s1 synced twice: a real 500, then a bogus 899 that gets ignored."""
    session.add(Store(id="s1", name="S1", type="shopify", base_url="https://s1.com"))
    session.commit()
    _sync(session, 500.0)
    _sync(session, 899.0)

    from sqlmodel import select

    product = session.exec(select(Product)).one()
    bogus = _snapshots(session, product.id)[-1]
    bogus.ignored = True
    session.add(bogus)
    session.commit()
    return product


def test_sync_compares_against_the_effective_latest(
    session: Session, synced_product: Product
):
    _sync(session, 500.0)

    prices = [s.price for s in _snapshots(session, synced_product.id)]
    assert prices == [500.0, 899.0]


def test_sync_records_a_real_move_past_an_ignored_reading(
    session: Session, synced_product: Product
):
    _sync(session, 450.0)

    prices = [s.price for s in _snapshots(session, synced_product.id)]
    assert prices == [500.0, 899.0, 450.0]
