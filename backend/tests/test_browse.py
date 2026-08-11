from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Game, PriceSnapshot, Store

from .factories import make_product


def _seed(session: Session):
    for sid, name in [("s1", "Store One"), ("s2", "Store Two")]:
        session.add(
            Store(id=sid, name=name, type="shopify", base_url=f"https://{sid}.com")
        )
    session.commit()

    products = [
        make_product(session, store_id="s1", external_id="e1", title="Catan"),
        make_product(session, store_id="s1", external_id="e2", title="Pandemic"),
        make_product(session, store_id="s2", external_id="e3", title="Azul"),
    ]

    prices = [
        (products[0].id, 30.0, True),
        (products[1].id, 50.0, False),
        (products[2].id, 20.0, True),
    ]
    for pid, price, avail in prices:
        session.add(PriceSnapshot(product_id=pid, price=price, available=avail))
    session.commit()

    return products


def _q(filters=None, sorts=None, page=1, limit=48):
    body = {"page": page, "limit": limit}
    if filters:
        body["filters"] = filters
    if sorts:
        body["sorts"] = sorts
    return body


def _cond(field, op, value):
    return {"type": "condition", "field": field, "op": op, "value": value}


def test_browse_all(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q())
    assert r.status_code == 200
    data = r.json()
    assert data["page"] == 1
    assert len(data["items"]) == 3


def test_browse_filter_store(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q(filters=_cond("store_id", "eq", "s1")))
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert set(titles) == {"Catan", "Pandemic"}


def test_browse_filter_query(client: TestClient, session: Session):
    _seed(session)
    r = client.post(
        "/api/browse/query", json=_q(filters=_cond("title", "contains", "cat"))
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["product"]["title"] == "Catan"


def test_browse_filter_in_stock(client: TestClient, session: Session):
    _seed(session)
    r = client.post(
        "/api/browse/query", json=_q(filters=_cond("available", "eq", True))
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "Pandemic" not in titles


def test_browse_filter_min_price(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q(filters=_cond("price", "gte", 35)))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["product"]["title"] == "Pandemic"


def test_browse_filter_max_price(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q(filters=_cond("price", "lte", 25)))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["product"]["title"] == "Azul"


def test_browse_sort_price_asc(client: TestClient, session: Session):
    _seed(session)
    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "price", "dir": "asc"}])
    )
    assert r.status_code == 200
    prices = [i["latest_price"]["price"] for i in r.json()["items"]]
    assert prices == sorted(prices)


def test_browse_sort_price_desc(client: TestClient, session: Session):
    _seed(session)
    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "price", "dir": "desc"}])
    )
    assert r.status_code == 200
    prices = [i["latest_price"]["price"] for i in r.json()["items"]]
    assert prices == sorted(prices, reverse=True)


def test_browse_pagination(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q(limit=2, page=1))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2

    r2 = client.post("/api/browse/query", json=_q(limit=2, page=2))
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 1


def test_browse_stores(client: TestClient, session: Session):
    _seed(session)
    r = client.get("/api/browse/stores")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_browse_no_bgg_by_default(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json=_q())
    items = r.json()["items"]
    assert all(i["bgg"] is None for i in items)


def test_browse_merged_game_one_card(client: TestClient, session: Session):
    """A game with listings at two stores (post-merge) is one card, not two."""
    session.add(
        Store(id="s1", name="Store One", type="shopify", base_url="https://s1.com")
    )
    session.add(
        Store(id="s2", name="Store Two", type="shopify", base_url="https://s2.com")
    )
    session.commit()

    game = Game(title="Poker Chip Set")
    session.add(game)
    session.flush()
    p1 = make_product(
        session, store_id="s1", external_id="e1", title="Poker Chip Set", game=game
    )
    p2 = make_product(
        session, store_id="s2", external_id="e2", title="Poker Chip Set", game=game
    )
    session.add(PriceSnapshot(product_id=p1.id, price=325.0, available=True))
    session.add(PriceSnapshot(product_id=p2.id, price=325.0, available=True))
    session.commit()

    r = client.post("/api/browse/query", json=_q())
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["items"][0]["compare"]["listing_count"] == 2


def _seed_merged_pair(session: Session):
    """One game sold at two stores, plus a single-store game."""
    for sid in ("s1", "s2"):
        session.add(
            Store(
                id=sid, name=sid.upper(), type="shopify", base_url=f"https://{sid}.com"
            )
        )
    session.commit()

    shared = Game(title="Poker Chip Set")
    session.add(shared)
    session.flush()
    p1 = make_product(
        session, store_id="s1", external_id="e1", title="Poker Chip Set", game=shared
    )
    p2 = make_product(
        session, store_id="s2", external_id="e2", title="Poker Chip Set", game=shared
    )
    p3 = make_product(session, store_id="s1", external_id="e3", title="Azul")
    for pid in (p1.id, p2.id, p3.id):
        session.add(PriceSnapshot(product_id=pid, price=100.0, available=True))
    session.commit()


def test_store_count_field_is_filterable(client: TestClient, session: Session):
    r = client.get("/api/browse/fields")
    field = next(f for f in r.json() if f["name"] == "store_count")
    assert field["type"] == "int"
    assert field["filterable"] and field["sortable"]


def test_filter_unmerged_games_only(client: TestClient, session: Session):
    _seed_merged_pair(session)
    r = client.post("/api/browse/query", json=_q(filters=_cond("store_count", "eq", 1)))
    assert r.status_code == 200
    data = r.json()
    assert [i["game"]["title"] for i in data["items"]] == ["Azul"]
    assert data["total"] == 1


def test_filter_merged_games_only(client: TestClient, session: Session):
    _seed_merged_pair(session)
    r = client.post("/api/browse/query", json=_q(filters=_cond("store_count", "gt", 1)))
    assert [i["game"]["title"] for i in r.json()["items"]] == ["Poker Chip Set"]


def test_store_count_counts_stores_not_listings(client: TestClient, session: Session):
    """Two listings at one store is still one store — that game is unmerged."""
    session.add(Store(id="s1", name="S1", type="shopify", base_url="https://s1.com"))
    session.commit()
    game = Game(title="Catan")
    session.add(game)
    session.flush()
    a = make_product(session, store_id="s1", external_id="a", title="Catan", game=game)
    b = make_product(session, store_id="s1", external_id="b", title="Catan", game=game)
    session.add(PriceSnapshot(product_id=a.id, price=10.0, available=True))
    session.add(PriceSnapshot(product_id=b.id, price=10.0, available=True))
    session.commit()

    r = client.post("/api/browse/query", json=_q(filters=_cond("store_count", "eq", 1)))
    assert [i["game"]["title"] for i in r.json()["items"]] == ["Catan"]
