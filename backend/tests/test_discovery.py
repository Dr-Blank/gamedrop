"""Discovery through browse filters + the ranked global search."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Game, PriceSnapshot, Store, WatchlistItem

from .factories import make_product


def _seed(session: Session):
    session.add(
        Store(id="s1", name="Store One", type="shopify", base_url="https://s1.com")
    )
    session.commit()

    products = [
        make_product(session, external_id="e1", title="Catan"),
        make_product(session, external_id="e2", title="Pandemic"),
        make_product(session, external_id="e3", title="Azul"),
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


def test_browse_finds_price_drops(client: TestClient, session: Session):
    """Drops are a filter, not a feed: cheaper than the previous snapshot."""
    _seed(session)
    items = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "price_pct_change",
                "op": "lt",
                "value": 0,
            },
            "sorts": [{"field": "price_pct_change", "dir": "asc"}],
        },
    ).json()["items"]
    titles = [i["product"]["title"] for i in items]
    assert "Catan" in titles
    assert "Pandemic" not in titles  # price rose


def test_browse_orders_new_arrivals_by_first_seen(client: TestClient, session: Session):
    _seed(session)
    items = client.post(
        "/api/browse/query",
        json={"sorts": [{"field": "first_seen", "dir": "desc"}]},
    ).json()["items"]
    # Azul was first seen last → should lead.
    assert items[0]["product"]["title"] == "Azul"


def test_browse_finds_discounted_listings(client: TestClient, session: Session):
    _seed(session)
    items = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "discount_pct",
                "op": "gt",
                "value": 0,
            }
        },
    ).json()["items"]
    assert [i["product"]["title"] for i in items] == ["Azul"]
    assert items[0]["discount_pct"] == 50.0


def test_search_matches_title(client: TestClient, session: Session):
    _seed(session)
    items = client.get("/api/search?q=cat").json()["items"]
    assert [i["product"]["title"] for i in items] == ["Catan"]


def test_search_blank_returns_empty(client: TestClient, session: Session):
    _seed(session)
    assert client.get("/api/search?q=").json()["items"] == []


def test_browse_keeps_hidden_games_behind_the_visible_ones(
    client: TestClient, session: Session
):
    """Scrolling to the end of a view still turns up what you hid."""
    products = _seed(session)
    hidden_game = session.get(Game, products[0].game_id)
    hidden_game.hidden = True
    session.add(hidden_game)
    session.commit()

    body = {"hidden_last": True, "sorts": [{"field": "title", "dir": "asc"}]}
    res = client.post("/api/browse/query", json=body).json()
    titles = [i["product"]["title"] for i in res["items"]]
    assert "Catan" in titles
    assert titles[-1] == "Catan"  # hidden, so it sorts behind Azul and Pandemic
    assert res["total"] == 3


def test_browse_leaves_hidden_games_out_by_default(
    client: TestClient, session: Session
):
    products = _seed(session)
    game = session.get(Game, products[0].game_id)
    game.hidden = True
    session.add(game)
    session.commit()

    res = client.post("/api/browse/query", json={}).json()
    assert "Catan" not in [i["product"]["title"] for i in res["items"]]
    assert res["total"] == 2


def test_browse_finds_watched_games(client: TestClient, session: Session):
    """The watchlist page is a filter too, and its cards name the watch."""
    products = _seed(session)
    session.add(WatchlistItem(game_id=products[0].game_id))
    session.commit()

    items = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "is_watched",
                "op": "eq",
                "value": True,
            }
        },
    ).json()["items"]
    assert [i["product"]["title"] for i in items] == ["Catan"]
    assert items[0]["watchlist"]["active"] is True
