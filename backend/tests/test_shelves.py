"""Shelf CRUD, ordering and home-page visibility."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Shelf


def _shelves(session: Session, *names: str) -> list[Shelf]:
    made = []
    for pos, name in enumerate(names):
        shelf = Shelf(name=name, position=pos)
        session.add(shelf)
        made.append(shelf)
    session.commit()
    for s in made:
        session.refresh(s)
    return made


def test_reorder_sets_positions(client: TestClient, session: Session):
    a, b, c = _shelves(session, "A", "B", "C")
    r = client.post("/api/shelves/reorder", json={"ids": [c.id, a.id, b.id]})
    assert r.status_code == 200
    assert [s["name"] for s in r.json()] == ["C", "A", "B"]
    assert [s["position"] for s in r.json()] == [0, 1, 2]


def test_reorder_persists_in_listing(client: TestClient, session: Session):
    a, b, c = _shelves(session, "A", "B", "C")
    client.post("/api/shelves/reorder", json={"ids": [b.id, c.id, a.id]})
    r = client.get("/api/shelves/")
    assert [s["name"] for s in r.json()] == ["B", "C", "A"]


def test_reorder_partial_list_appends_rest(client: TestClient, session: Session):
    a, b, c = _shelves(session, "A", "B", "C")
    r = client.post("/api/shelves/reorder", json={"ids": [c.id]})
    assert [s["name"] for s in r.json()] == ["C", "A", "B"]
    assert a.id and b.id  # keep relative order of the untouched shelves


def test_reorder_unknown_id_404(client: TestClient, session: Session):
    a, _b, _c = _shelves(session, "A", "B", "C")
    r = client.post("/api/shelves/reorder", json={"ids": [a.id, 9999]})
    assert r.status_code == 404


def test_reorder_duplicate_ids_400(client: TestClient, session: Session):
    a, _b, _c = _shelves(session, "A", "B", "C")
    r = client.post("/api/shelves/reorder", json={"ids": [a.id, a.id]})
    assert r.status_code == 400


def test_patch_hidden_flag(client: TestClient, session: Session):
    a, _b = _shelves(session, "A", "B")
    r = client.patch(f"/api/shelves/{a.id}", json={"hidden": True})
    assert r.status_code == 200
    assert r.json()["hidden"] is True


def test_preview_excludes_hidden(client: TestClient, session: Session):
    a, _b = _shelves(session, "A", "B")
    client.patch(f"/api/shelves/{a.id}", json={"hidden": True})
    names = [row["shelf"]["name"] for row in client.get("/api/shelves/preview").json()]
    assert names == ["B"]


def test_listing_includes_hidden(client: TestClient, session: Session):
    a, _b = _shelves(session, "A", "B")
    client.patch(f"/api/shelves/{a.id}", json={"hidden": True})
    names = [s["name"] for s in client.get("/api/shelves/").json()]
    assert names == ["A", "B"]


def test_unhide_restores_to_preview(client: TestClient, session: Session):
    a, _b = _shelves(session, "A", "B")
    client.patch(f"/api/shelves/{a.id}", json={"hidden": True})
    client.patch(f"/api/shelves/{a.id}", json={"hidden": False})
    names = [row["shelf"]["name"] for row in client.get("/api/shelves/preview").json()]
    assert names == ["A", "B"]


def test_built_in_shelf_can_be_hidden_not_deleted(client: TestClient, session: Session):
    shelf = Shelf(name="Top Discounts", built_in=True)
    session.add(shelf)
    session.commit()
    session.refresh(shelf)

    assert client.delete(f"/api/shelves/{shelf.id}").status_code == 403
    assert (
        client.patch(f"/api/shelves/{shelf.id}", json={"hidden": True}).status_code
        == 200
    )
    assert client.get("/api/shelves/preview").json() == []


def test_new_shelf_defaults_to_visible(client: TestClient, session: Session):
    r = client.post("/api/shelves/", json={"name": "Fresh"})
    assert r.status_code == 201
    assert r.json()["hidden"] is False
