"""Out-of-stock placeholder prices from before a listing first stocks."""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.config import set_setting
from app.models import PriceSnapshot
from app.snapshots import IGNORE_PRE_STOCK

from .factories import make_product, make_store


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _listing(session: Session, readings, variant_id=None, product=None):
    """(price, available, hours_ago) readings, oldest first."""
    if product is None:
        make_store(session, "a")
        product = make_product(session, store_id="a", title="Ark")
    for price, available, hours_ago in readings:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                variant_id=variant_id,
                price=price,
                available=available,
                recorded_at=_now() - timedelta(hours=hours_ago),
            )
        )
    session.commit()
    return product


def _events(client):
    r = client.get("/api/timeline/events")
    assert r.status_code == 200, r.text
    return [(e["kind"], e["price"]) for e in r.json()["events"]]


def _history(client, product):
    r = client.get(f"/api/prices/product/{product.id}")
    return sorted(h["price"] for h in r.json()["history"])


def test_first_stock_is_an_arrival_not_a_rise(client, session):
    _listing(session, [(5800, False, 30), (5800, False, 20), (6000, True, 10)])
    assert _events(client) == [("listed", 6000)]


def test_placeholders_drop_out_of_the_history(client, session):
    product = _listing(session, [(0, False, 20), (500, True, 10)])
    assert _history(client, product) == [500]


def test_turning_it_off_restores_the_rise(client, session):
    set_setting(IGNORE_PRE_STOCK, "false")
    _listing(session, [(5800, False, 20), (6000, True, 10)])
    assert _events(client) == [("rise", 6000), ("listed", 5800)]


def test_selling_out_later_still_counts(client, session):
    _listing(session, [(500, True, 30), (450, False, 20), (500, True, 10)])
    assert [k for k, _ in _events(client)] == ["rise", "drop", "listed"]


def test_never_stocked_keeps_its_placeholders(client, session):
    product = _listing(session, [(5800, False, 20), (6000, False, 10)])
    assert _history(client, product) == [5800, 6000]
    assert [k for k, _ in _events(client)] == ["rise", "listed"]


def test_each_variant_stocks_on_its_own(client, session):
    product = _listing(session, [(100, True, 30)], variant_id="a")
    _listing(session, [(0, False, 20), (200, True, 10)], "b", product)
    assert sorted(_events(client)) == [("listed", 100), ("listed", 200)]


def test_an_ignored_stock_reading_is_not_the_first_stock(client, session):
    product = _listing(
        session, [(0, False, 30), (9999, True, 20), (0, False, 15), (500, True, 10)]
    )
    typo = session.exec(select(PriceSnapshot).where(PriceSnapshot.price == 9999)).one()
    client.put(f"/api/prices/snapshot/{typo.id}/ignore")

    assert _history(client, product) == [500]
    assert _events(client) == [("listed", 500)]


def test_setting_defaults_on_and_saves(client):
    assert client.get("/api/settings/").json()[IGNORE_PRE_STOCK] is True

    client.put("/api/settings/", json={IGNORE_PRE_STOCK: False})
    assert client.get("/api/settings/").json()[IGNORE_PRE_STOCK] is False


def test_saving_other_settings_leaves_it_alone(client):
    client.put("/api/settings/", json={IGNORE_PRE_STOCK: False})
    client.put("/api/settings/", json={"ntfy_topic": "alerts"})
    assert client.get("/api/settings/").json()[IGNORE_PRE_STOCK] is False
