from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, ProductOverride, Store, WatchlistItem

from .factories import make_product


def _seed(session: Session):
    store = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(store)
    session.commit()

    product = make_product(session, external_id="ext-1", title="Catan")

    for price in [25.0, 28.0, 22.0]:
        session.add(PriceSnapshot(product_id=product.id, price=price))
    session.commit()

    return product


def test_price_history(client: TestClient, session: Session):
    product = _seed(session)
    r = client.get(f"/api/prices/product/{product.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["product"]["id"] == product.id
    assert len(data["history"]) == 3


def test_price_history_limit(client: TestClient, session: Session):
    product = _seed(session)
    r = client.get(f"/api/prices/product/{product.id}?limit=2")
    assert r.status_code == 200
    assert len(r.json()["history"]) == 2


def test_price_history_not_found(client: TestClient):
    r = client.get("/api/prices/product/999")
    assert r.status_code == 404


def test_search_by_name(client: TestClient, session: Session):
    _seed(session)
    r = client.get("/api/prices/search?q=catan")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["product"]["title"] == "Catan"


def test_search_by_name_no_match(client: TestClient, session: Session):
    _seed(session)
    r = client.get("/api/prices/search?q=monopoly")
    assert r.status_code == 200
    assert r.json() == []


def test_search_filter_by_store(client: TestClient, session: Session):
    _seed(session)
    r = client.get("/api/prices/search?q=catan&store_id=s1")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r2 = client.get("/api/prices/search?q=catan&store_id=other")
    assert r.status_code == 200
    assert r2.json() == []


def test_price_history_includes_override(client: TestClient, session: Session):
    product = _seed(session)
    session.add(ProductOverride(product_id=product.id, override_price=19.0))
    session.commit()

    r = client.get(f"/api/prices/product/{product.id}")
    assert r.status_code == 200
    assert r.json()["override"]["override_price"] == 19.0


def test_price_history_includes_the_game(client: TestClient, session: Session):
    product = _seed(session)
    data = client.get(f"/api/prices/product/{product.id}").json()
    assert data["game"]["id"] == product.game_id


def test_price_history_no_override_returns_null(client: TestClient, session: Session):
    product = _seed(session)
    r = client.get(f"/api/prices/product/{product.id}")
    assert r.status_code == 200
    assert r.json()["override"] is None


def test_price_history_includes_watchlist_item(client: TestClient, session: Session):
    product = _seed(session)
    session.add(WatchlistItem(game_id=product.game_id, target_price=20.0, active=True))
    session.commit()

    r = client.get(f"/api/prices/product/{product.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["watchlist_item"]["target_price"] == 20.0


def test_price_history_inactive_watchlist_not_returned(
    client: TestClient, session: Session
):
    product = _seed(session)
    session.add(WatchlistItem(game_id=product.game_id, active=False))
    session.commit()

    r = client.get(f"/api/prices/product/{product.id}")
    assert r.status_code == 200
    assert r.json()["watchlist_item"] is None
