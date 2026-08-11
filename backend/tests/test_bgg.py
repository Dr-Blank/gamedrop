"""BGG linking. The link belongs to the game, so a listing id resolves to one."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Game, Product, Store

from .factories import make_product, make_store


def _store(session: Session) -> Store:
    return make_store(session)


def _product(session: Session, title: str, bgg_id: int | None = None) -> Product:
    return make_product(session, title=title, external_id=title, bgg_id=bgg_id)


def _game(session: Session, product: Product) -> Game:
    return session.get(Game, product.game_id)


def test_unlinked_returns_only_unlinked(client: TestClient, session: Session):
    _store(session)
    unlinked = _product(session, "Catan")
    _product(session, "Ticket to Ride", bgg_id=9209)

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["games"][0]["id"] == unlinked.game_id
    assert data["games"][0]["product_id"] == unlinked.id
    assert data["games"][0]["title"] == "Catan"


def test_unlinked_excludes_hidden(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Hidden Game")
    _game(session, p).hidden = True
    session.commit()

    r = client.get("/api/bgg/unlinked")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_unlinked_counts_a_merged_game_once(client: TestClient, session: Session):
    _store(session)
    make_store(session, "s2")
    a = _product(session, "Azul")
    b = make_product(session, store_id="s2", title="Azul", external_id="azul-2")
    b.game_id = a.game_id
    session.add(b)
    session.commit()

    data = client.get("/api/bgg/unlinked").json()
    assert data["total"] == 1
    assert len(data["games"]) == 1


def test_unlinked_pagination(client: TestClient, session: Session):
    _store(session)
    for i in range(5):
        _product(session, f"Game {i}")

    data = client.get("/api/bgg/unlinked?page=1&limit=3").json()
    assert data["total"] == 5
    assert len(data["games"]) == 3
    assert len(client.get("/api/bgg/unlinked?page=2&limit=3").json()["games"]) == 2


def test_link_bgg_via_listing_links_the_game(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Wingspan")

    r = client.post(f"/api/bgg/game/266192/link/{p.id}")
    assert r.status_code == 200
    assert r.json()["game_id"] == p.game_id
    session.expire_all()
    assert _game(session, p).bgg_id == 266192


def test_link_covers_every_listing_of_the_game(client: TestClient, session: Session):
    _store(session)
    make_store(session, "s2")
    a = _product(session, "Catan")
    b = make_product(session, store_id="s2", title="Catan", external_id="catan-2")
    b.game_id = a.game_id
    session.add(b)
    session.commit()

    client.post(f"/api/bgg/game/13/link/{a.id}")
    session.expire_all()
    assert _game(session, b).bgg_id == 13


def test_link_product_not_found(client: TestClient):
    assert client.post("/api/bgg/game/12345/link/99999").status_code == 404


def test_unlink_bgg(client: TestClient, session: Session):
    _store(session)
    p = _product(session, "Wingspan", bgg_id=266192)

    r = client.delete(f"/api/bgg/link/{p.id}")
    assert r.status_code == 200
    session.expire_all()
    assert _game(session, p).bgg_id is None


def test_unlink_bgg_not_found(client: TestClient):
    assert client.delete("/api/bgg/link/99999").status_code == 404
