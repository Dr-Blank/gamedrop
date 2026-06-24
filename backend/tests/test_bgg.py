from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Product, ProductOverride, Store


def _store(session: Session) -> Store:
    s = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(s)
    session.commit()
    return s


def _product(session: Session, title: str, bgg_id: int | None = None) -> Product:
    p = Product(store_id="s1", external_id=title, title=title, bgg_id=bgg_id)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_unlinked_returns_only_unlinked(client: TestClient, session: Session):
    _store(session)
    unlinked = _product(session, "Catan")
    _product(session, "Ticket to Ride", bgg_id=9209)

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["products"][0]["id"] == unlinked.id
    assert data["products"][0]["title"] == "Catan"


def test_unlinked_excludes_override_linked(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Pandemic")
    session.add(ProductOverride(product_id=p.id, bgg_id=30549))
    session.commit()

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_unlinked_includes_override_without_bgg(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Azul")
    session.add(ProductOverride(product_id=p.id, title="Azul Fixed"))
    session.commit()

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_unlinked_excludes_hidden(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Hidden Game")
    p.hidden = True
    session.add(p)
    session.commit()

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_unlinked_pagination(client: TestClient, session: Session):
    _store(session)
    for i in range(5):
        _product(session, f"Game {i}")

    r = client.get("/api/bgg/unlinked?page=1&limit=3")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["products"]) == 3

    r2 = client.get("/api/bgg/unlinked?page=2&limit=3")
    assert len(r2.json()["products"]) == 2


def test_link_game_to_product(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Wingspan")

    r = client.post(f"/api/bgg/game/266192/link/{p.id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    session.refresh(p)
    assert p.bgg_id == 266192


def test_link_game_product_not_found(client: TestClient):
    r = client.post("/api/bgg/game/12345/link/99999")
    assert r.status_code == 404


def test_unlink_bgg(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Wingspan", bgg_id=266192)

    r = client.delete(f"/api/bgg/link/{p.id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    session.refresh(p)
    assert p.bgg_id is None


def test_unlink_bgg_clears_override_bgg_id(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Wingspan", bgg_id=266192)
    session.add(ProductOverride(product_id=p.id, bgg_id=266192))
    session.commit()

    r = client.delete(f"/api/bgg/link/{p.id}")
    assert r.status_code == 200

    session.refresh(p)
    assert p.bgg_id is None
    ov = session.get(ProductOverride, p.id)
    assert ov is not None
    assert ov.bgg_id is None


def test_unlink_bgg_not_found(client: TestClient):
    r = client.delete("/api/bgg/link/99999")
    assert r.status_code == 404
