from unittest.mock import ANY, patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Game, PriceSnapshot, Product, Store, WatchlistItem
from app.scraper import _check_watchlist

from .factories import make_product, make_store


def _seed(session: Session) -> int:
    store = Store(id="s1", name="S1", type="shopify", base_url="https://s1.com")
    session.add(store)
    session.commit()

    product = make_product(session, external_id="ext-1", title="Catan")
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
    product = session.get(Product, pid)
    r = client.post("/api/watchlist/", json={"product_id": pid, "target_price": 20.0})
    assert r.status_code == 200
    data = r.json()
    assert data["game_id"] == product.game_id
    assert data["target_price"] == 20.0
    assert data["active"] is True


def test_watching_one_shop_watches_the_game(client: TestClient, session: Session):
    """Two shops, one game: watching either marks both as watched."""
    pid = _seed(session)
    product = session.get(Product, pid)
    make_store(session, "s2")
    other = make_product(
        session,
        store_id="s2",
        title="Catan",
        external_id="e2",
        game=session.get(Game, product.game_id),
    )

    client.post("/api/watchlist/", json={"product_id": pid})
    watched = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "is_watched",
                "op": "eq",
                "value": True,
            }
        },
    ).json()
    assert len(watched["items"]) == 1
    item = watched["items"][0]
    assert item["game"]["id"] == product.game_id
    offer_ids = {o["product_id"] for o in item["compare"]["offers"]}
    assert {pid, other.id} <= offer_ids


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


def _seed_for_notify(session: Session, target_price: float | None = None):
    store = Store(id="sn1", name="SN1", type="shopify", base_url="https://sn1.com")
    session.add(store)
    session.commit()

    product = make_product(
        session,
        store_id="sn1",
        external_id="ext-n1",
        title="Catan Notify",
        url="https://sn1.com/catan",
    )

    watchlist_item = WatchlistItem(
        game_id=product.game_id, target_price=target_price, active=True
    )
    session.add(watchlist_item)
    session.commit()

    return product


def test_price_drop_triggers_notification(session: Session):
    product = _seed_for_notify(session)
    old_snap = PriceSnapshot(product_id=product.id, price=100.0, available=True)
    session.add(old_snap)
    session.commit()
    session.refresh(old_snap)

    new_snap = PriceSnapshot(product_id=product.id, price=80.0, available=True)
    session.add(new_snap)
    session.flush()

    with patch("app.scraper.notify_price_drop") as mock_notify:
        _check_watchlist(session, product, old_snap, new_snap)
        mock_notify.assert_called_once_with(
            product.title,
            100.0,
            80.0,
            product.url,
            product.store_id,
            product_id=product.id,
            game_id=ANY,
            recorded_at=ANY,
        )


def test_back_in_stock_triggers_notification(session: Session):
    product = _seed_for_notify(session)
    old_snap = PriceSnapshot(product_id=product.id, price=100.0, available=False)
    session.add(old_snap)
    session.commit()
    session.refresh(old_snap)

    new_snap = PriceSnapshot(product_id=product.id, price=100.0, available=True)
    session.add(new_snap)
    session.flush()

    with patch("app.scraper.notify_back_in_stock") as mock_notify:
        _check_watchlist(session, product, old_snap, new_snap)
        mock_notify.assert_called_once_with(
            product.title,
            100.0,
            product.url,
            product.store_id,
            product_id=product.id,
            game_id=ANY,
            recorded_at=ANY,
        )


def test_target_price_hit_triggers_notification(session: Session):
    product = _seed_for_notify(session, target_price=70.0)
    old_snap = PriceSnapshot(product_id=product.id, price=100.0, available=True)
    session.add(old_snap)
    session.commit()
    session.refresh(old_snap)

    new_snap = PriceSnapshot(product_id=product.id, price=65.0, available=True)
    session.add(new_snap)
    session.flush()

    with patch("app.scraper.notify_target_reached") as mock_notify:
        _check_watchlist(session, product, old_snap, new_snap)
        mock_notify.assert_called_once_with(
            product.title,
            70.0,
            65.0,
            product.url,
            product.store_id,
            product_id=product.id,
            game_id=ANY,
            recorded_at=ANY,
        )


def test_no_notification_price_increase(session: Session):
    product = _seed_for_notify(session)
    old_snap = PriceSnapshot(product_id=product.id, price=80.0, available=True)
    session.add(old_snap)
    session.commit()
    session.refresh(old_snap)

    new_snap = PriceSnapshot(product_id=product.id, price=100.0, available=True)
    session.add(new_snap)
    session.flush()

    with patch("app.scraper.notify_price_drop") as mock_notify:
        _check_watchlist(session, product, old_snap, new_snap)
        mock_notify.assert_not_called()
