"""Out-of-stock placeholder prices from before a listing first stocks."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app.config import set_setting
from app.models import PriceSnapshot
from app.snapshots import IGNORE_PRE_STOCK, MANUAL, effective, split_ignored

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


def test_never_stocked_keeps_only_its_latest_placeholder(client, session):
    product = _listing(session, [(10000, False, 20), (2500, False, 10)])
    assert _history(client, product) == [2500]
    assert _events(client) == [("listed", 2500)]


def test_never_stocked_variant_beside_a_stocked_one(client, session):
    product = _listing(session, [(100, True, 30)], variant_id="a")
    _listing(session, [(900, False, 20), (300, False, 10)], "b", product)
    assert sorted(_events(client)) == [("listed", 100), ("listed", 300)]


def _ignored(client, product):
    r = client.get(f"/api/prices/product/{product.id}")
    return [(h["price"], h["ignored"]) for h in r.json()["ignored"]]


def test_skipped_placeholders_are_listed_as_ignored(client, session):
    product = _listing(session, [(10000, False, 20), (2500, False, 10)])
    assert _ignored(client, product) == [(10000, False)]


def test_restoring_a_skipped_placeholder_counts_it(client, session):
    product = _listing(session, [(10000, False, 20), (2500, False, 10)])
    placeholder = session.exec(
        select(PriceSnapshot).where(PriceSnapshot.price == 10000)
    ).one()
    client.delete(f"/api/prices/snapshot/{placeholder.id}/ignore")

    assert _history(client, product) == [2500, 10000]
    assert _ignored(client, product) == []
    assert [k for k, _ in _events(client)] == ["drop", "listed"]


def test_game_series_marks_skipped_readings(client, session):
    product = _listing(session, [(0, False, 20), (500, True, 10)])
    r = client.get(f"/api/games/{product.game_id}")
    (series,) = r.json()["series"]
    assert [(h["price"], h["ignored"]) for h in series["ignored"]] == [(0, False)]


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


PARITY_CASES = {
    "tied_latest_placeholders": [
        (None, False, 30, {}),
        (None, False, 20, {}),
        (None, False, 20, {}),
    ],
    "null_variant_beside_named": [
        ("a", False, 30, {}),
        ("a", True, 20, {}),
        ("a", False, 10, {}),
        (None, False, 30, {}),
        (None, False, 10, {}),
    ],
    "all_ignored_fallback": [
        (None, False, 20, {"ignored": True}),
        (None, False, 10, {"ignored": True}),
    ],
    "ignored_latest": [
        (None, False, 30, {}),
        (None, False, 20, {}),
        (None, False, 10, {"ignored": True}),
    ],
    "confirmed_placeholder": [
        (None, False, 30, {"confirmed": True}),
        (None, False, 20, {}),
        (None, True, 10, {}),
    ],
    "manual_before_stock": [
        (None, False, 30, {"source": MANUAL}),
        (None, False, 20, {}),
        (None, True, 10, {}),
    ],
}


@pytest.mark.parametrize("case", PARITY_CASES)
def test_sql_and_python_rules_agree(session, case):
    make_store(session, "a")
    product = make_product(session, store_id="a", title=case)
    base = datetime(2026, 1, 1)
    for i, (variant_id, available, hours_ago, extra) in enumerate(PARITY_CASES[case]):
        session.add(
            PriceSnapshot(
                product_id=product.id,
                variant_id=variant_id,
                price=100 + i,
                available=available,
                recorded_at=base - timedelta(hours=hours_ago),
                **extra,
            )
        )
    session.commit()
    mine = PriceSnapshot.product_id == product.id

    in_sql = session.exec(
        select(PriceSnapshot.id).where(mine, effective(pre_stock=True))
    ).all()
    snaps = session.exec(select(PriceSnapshot).where(mine)).all()
    in_python = [s.id for s in split_ignored(list(snaps), pre_stock=True)[0]]

    assert sorted(in_sql) == sorted(in_python)
