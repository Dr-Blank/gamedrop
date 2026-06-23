import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import PriceSnapshot, Product, Store


def _seed(session: Session):
    session.add(Store(id="s1", name="S1", type="shopify", base_url="https://s1.com"))
    session.commit()
    p = Product(store_id="s1", external_id="e1", title="Catan")
    session.add(p)
    session.commit()
    session.refresh(p)
    session.add(PriceSnapshot(product_id=p.id, price=40.0, available=True))
    session.commit()
    return p


def test_set_override_creates(client: TestClient, session: Session):
    p = _seed(session)
    r = client.put(
        f"/api/products/{p.id}/override",
        json={"title": "Catan Deluxe", "note": "fixed title"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Catan Deluxe"
    assert data["note"] == "fixed title"
    assert data["product_id"] == p.id


def test_set_override_updates_existing(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"title": "First"})
    r = client.put(f"/api/products/{p.id}/override", json={"title": "Second"})
    assert r.status_code == 200
    assert r.json()["title"] == "Second"


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
    r = client.put("/api/products/99999/override", json={"title": "x"})
    assert r.status_code == 404


def test_clear_override(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"title": "Override"})
    r = client.delete(f"/api/products/{p.id}/override")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_clear_override_not_found(client: TestClient, session: Session):
    p = _seed(session)
    r = client.delete(f"/api/products/{p.id}/override")
    assert r.status_code == 404


def test_override_appears_in_browse(client: TestClient, session: Session):
    p = _seed(session)
    client.put(f"/api/products/{p.id}/override", json={"title": "Catan Deluxe"})
    r = client.post("/api/browse/query", json={})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    ov = items[0]["override"]
    assert ov is not None
    assert ov["title"] == "Catan Deluxe"


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
