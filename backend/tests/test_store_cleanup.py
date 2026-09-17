from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import (
    CartItem,
    MergeRejection,
    NotificationLog,
    PriceSnapshot,
    Product,
    ProductOverride,
    WatchListingState,
)

from .factories import make_product, make_store, watch


def _seed_listing(session: Session, store_id: str = "s1", title: str = "Catan"):
    """A listing with every kind of row that hangs off one."""
    product = make_product(session, store_id=store_id, title=title)
    item = watch(session, product)
    session.add(PriceSnapshot(product_id=product.id, price=30.0))
    session.add(ProductOverride(product_id=product.id, override_price=25.0))
    session.add(WatchListingState(watch_id=item.id, product_id=product.id))
    session.add(
        NotificationLog(
            product_id=product.id, kind="price_drop", title="t", message="m"
        )
    )
    session.add(CartItem(game_id=product.game_id, product_id=product.id))
    session.commit()
    return product


def test_removing_a_store_keeps_its_listings_by_default(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    _seed_listing(session)

    assert client.delete("/api/stores/s1").json() == {
        "ok": True,
        "deleted_listings": 0,
    }
    assert len(session.exec(select(Product)).all()) == 1


def test_removing_a_store_can_take_its_listings_with_it(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    _seed_listing(session)

    body = client.delete("/api/stores/s1?delete_listings=true").json()

    assert body == {"ok": True, "deleted_listings": 1}
    assert session.exec(select(Product)).all() == []


def test_deleting_listings_clears_the_rows_keyed_on_them(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    _seed_listing(session)

    client.delete("/api/stores/s1?delete_listings=true")

    assert session.exec(select(PriceSnapshot)).all() == []
    assert session.exec(select(ProductOverride)).all() == []
    assert session.exec(select(WatchListingState)).all() == []


def test_queue_and_notification_history_survive_the_delete(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    _seed_listing(session)

    client.delete("/api/stores/s1?delete_listings=true")

    queued = session.exec(select(CartItem)).one()
    logged = session.exec(select(NotificationLog)).one()
    assert queued.product_id is None
    assert logged.product_id is None


def test_merge_rejections_go_with_either_listing(client: TestClient, session: Session):
    make_store(session, "s1")
    make_store(session, "s2")
    a = make_product(session, store_id="s1", title="Catan")
    b = make_product(session, store_id="s2", title="Catan Seafarers")
    session.add(
        MergeRejection(product_a_id=min(a.id, b.id), product_b_id=max(a.id, b.id))
    )
    session.commit()

    client.delete("/api/stores/s2?delete_listings=true")

    assert session.exec(select(MergeRejection)).all() == []


def test_only_the_removed_stores_listings_go(client: TestClient, session: Session):
    make_store(session, "s1")
    make_store(session, "s2")
    make_product(session, store_id="s1", title="Catan")
    keeper = make_product(session, store_id="s2", title="Azul")

    client.delete("/api/stores/s1?delete_listings=true")

    remaining = session.exec(select(Product)).all()
    assert [p.id for p in remaining] == [keeper.id]


def test_orphans_are_counted_per_missing_store(client: TestClient, session: Session):
    make_store(session, "s1")
    make_store(session, "s2")
    make_product(session, store_id="s1", title="Catan")
    make_product(session, store_id="s1", title="Azul")
    make_product(session, store_id="s2", title="Pandemic")
    client.delete("/api/stores/s1")

    body = client.get("/api/stores/orphans").json()

    assert body["listings"] == 2
    assert body["games"] == 2
    assert body["stores"] == [{"store_id": "s1", "listings": 2}]


def test_nothing_is_orphaned_while_every_store_is_configured(client: TestClient):
    assert client.get("/api/stores/orphans").json() == {
        "listings": 0,
        "games": 0,
        "stores": [],
    }


def test_cleanup_removes_every_orphan_and_leaves_the_rest(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    make_store(session, "s2")
    _seed_listing(session, store_id="s1")
    keeper = make_product(session, store_id="s2", title="Azul")
    client.delete("/api/stores/s1")

    assert client.post("/api/stores/orphans/cleanup").json() == {"deleted": 1}
    assert [p.id for p in session.exec(select(Product)).all()] == [keeper.id]
    assert client.get("/api/stores/orphans").json()["listings"] == 0


def test_a_store_reports_how_many_listings_it_has(client: TestClient, session: Session):
    make_store(session, "s1")
    make_product(session, store_id="s1", title="Catan")
    make_product(session, store_id="s1", title="Azul")

    assert client.get("/api/stores/").json()[0]["listing_count"] == 2


def test_browse_can_filter_down_to_orphaned_listings(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    make_store(session, "s2")
    orphan = make_product(session, store_id="s1", title="Catan")
    make_product(session, store_id="s2", title="Azul")
    client.delete("/api/stores/s1")

    body = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "is_orphaned",
                "op": "eq",
                "value": True,
            }
        },
    ).json()

    assert body["total"] == 1
    assert [c["product"]["id"] for c in body["items"]] == [orphan.id]
