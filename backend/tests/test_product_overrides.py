import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, Store

from .factories import make_product


def _seed(session: Session):
    session.add(Store(id="s1", name="S1", type="shopify", base_url="https://s1.com"))
    session.commit()
    p = make_product(session, external_id="e1", title="Catan")
    session.add(PriceSnapshot(product_id=p.id, price=40.0, available=True))
    session.commit()
    return p


def test_set_override_creates(client: TestClient, session: Session):
    p = _seed(session)
    r = client.put(
        f"/api/products/{p.id}/override",
        json={"url": "https://s1.com/fixed", "override_price": 33.0},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["url"] == "https://s1.com/fixed"
    assert data["product_id"] == p.id


def test_set_override_updates_existing(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"override_price": 10.0})
    r = client.put(f"/api/products/{p.id}/override", json={"override_price": 20.0})
    assert r.status_code == 200
    assert r.json()["override_price"] == pytest.approx(20.0)


def test_rename_is_a_game_edit(client: TestClient, session: Session):
    """Names belong to the game, so renaming is a PATCH on it."""
    p = _seed(session)
    r = client.patch(f"/api/games/{p.game_id}", json={"title": "Catan Deluxe"})
    assert r.status_code == 200
    assert r.json()["game"]["title"] == "Catan Deluxe"


def test_set_override_price_and_stock(client: TestClient, session: Session):
    p = _seed(session)
    r = client.put(
        f"/api/products/{p.id}/override",
        json={"override_price": 35.0, "override_available": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["override_price"] == pytest.approx(35.0)
    assert data["override_available"] is False


def test_set_override_product_not_found(client: TestClient):
    r = client.put("/api/products/99999/override", json={"override_price": 5.0})
    assert r.status_code == 404


def test_clear_override(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"override_price": 5.0})
    r = client.delete(f"/api/products/{p.id}/override")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_clear_override_not_found(client: TestClient, session: Session):
    p = _seed(session)
    r = client.delete(f"/api/products/{p.id}/override")
    assert r.status_code == 404


def test_override_appears_in_browse(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"override_price": 33.0})
    r = client.post("/api/browse/query", json={})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["override"]["override_price"] == pytest.approx(33.0)


def test_renamed_game_appears_in_browse(client: TestClient, session: Session):
    p = _seed(session)
    client.patch(f"/api/games/{p.game_id}", json={"title": "Catan Deluxe"})
    items = client.post("/api/browse/query", json={}).json()["items"]
    assert items[0]["game"]["title"] == "Catan Deluxe"


def test_no_override_in_browse_by_default(client: TestClient, session: Session):
    _seed(session)
    r = client.post("/api/browse/query", json={})
    items = r.json()["items"]
    assert items[0]["override"] is None


def test_override_cleared_not_in_browse(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"title": "X"})
    client.delete(f"/api/products/{p.id}/override")
    r = client.post("/api/browse/query", json={})
    assert r.json()["items"][0]["override"] is None
