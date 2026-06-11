from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, Product, Store


def _seed(session: Session) -> int:
    store = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(store)
    session.commit()

    product = Product(store_id="s1", external_id="ext-1", title="Catan")
    session.add(product)
    session.commit()
    session.refresh(product)

    session.add(PriceSnapshot(product_id=product.id, price=30.0))
    session.commit()

    return product.id


def test_list_empty(client: TestClient):
    r = client.get("/api/watchlist/")
    assert r.status_code == 200
    assert r.json() == []


def test_add_to_watchlist(client: TestClient, session: Session):
    pid = _seed(session)
    r = client.post("/api/watchlist/", json={"product_id": pid, "target_price": 20.0})
    assert r.status_code == 200
    data = r.json()
    assert data["product_id"] == pid
    assert data["target_price"] == 20.0
    assert data["active"] is True


def test_add_nonexistent_product(client: TestClient):
    r = client.post("/api/watchlist/", json={"product_id": 999})
    assert r.status_code == 404


def test_add_duplicate_updates(client: TestClient, session: Session):
    pid = _seed(session)
    client.post("/api/watchlist/", json={"product_id": pid, "target_price": 20.0})
    r = client.post("/api/watchlist/", json={"product_id": pid, "target_price": 15.0})
    assert r.status_code == 200
    assert r.json()["target_price"] == 15.0

    items = client.get("/api/watchlist/").json()
    assert len(items) == 1


def test_list_watchlist_includes_product(client: TestClient, session: Session):
    pid = _seed(session)
    client.post("/api/watchlist/", json={"product_id": pid})
    items = client.get("/api/watchlist/").json()
    assert len(items) == 1
    assert items[0]["product"]["id"] == pid


def test_remove_from_watchlist(client: TestClient, session: Session):
    pid = _seed(session)
    item = client.post("/api/watchlist/", json={"product_id": pid}).json()
    r = client.delete(f"/api/watchlist/{item['id']}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    assert client.get("/api/watchlist/").json() == []


def test_remove_not_found(client: TestClient):
    r = client.delete("/api/watchlist/999")
    assert r.status_code == 404


def test_update_watchlist(client: TestClient, session: Session):
    pid = _seed(session)
    item = client.post(
        "/api/watchlist/", json={"product_id": pid, "target_price": 20.0}
    ).json()
    r = client.patch(
        f"/api/watchlist/{item['id']}", json={"product_id": pid, "target_price": 10.0}
    )
    assert r.status_code == 200
    assert r.json()["target_price"] == 10.0
