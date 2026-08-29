"""Filtering the catalog by when a game's price or stock changed.

Covers the relative date vocabulary (`now`, `today`, `-7d`), the change window
that asks whether any change landed inside a period, and the `last_change_at`
field the results are ordered by.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.filter_engine import (
    ChangeWindow,
    Condition,
    Group,
    SortSpec,
    _to_datetime,
)
from app.models import Game, PriceSnapshot, Store
from app.repositories.catalog import (
    count_products,
    get_field_registry,
    query_products,
)

from .factories import make_product


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _store(session: Session, sid: str = "s1"):
    session.add(Store(id=sid, name=sid, type="shopify", base_url=f"https://{sid}.com"))
    session.commit()


def _listing(session: Session, title: str, readings: list[tuple[float, datetime]]):
    """A listing with the given (price, recorded_at) history, oldest first."""
    product = make_product(session, store_id="s1", external_id=title, title=title)
    for price, recorded_at in readings:
        session.add(
            PriceSnapshot(product_id=product.id, price=price, recorded_at=recorded_at)
        )
    session.commit()
    return product


def quiet_game(session: Session, product):
    """The game a listing belongs to, for a second shop to share."""
    return session.get(Game, product.game_id)


def _titles(session: Session, node) -> list[str]:
    return [g.title for _, _, g in query_products(session, filter_node=node)]


# ---------------------------------------------------------------------------
# Relative date vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "delta"),
    [
        ("-30m", timedelta(minutes=30)),
        ("-6h", timedelta(hours=6)),
        ("-1d", timedelta(days=1)),
        ("-2w", timedelta(weeks=2)),
        ("-1mo", timedelta(days=30)),
        ("-1y", timedelta(days=365)),
    ],
)
def test_relative_offsets_resolve_backwards_from_now(value, delta):
    assert abs(_to_datetime(value) - (_now() - delta)) < timedelta(seconds=5)


def test_relative_offset_can_point_forwards():
    assert _to_datetime("+1d") - _now() > timedelta(hours=23)


@pytest.mark.parametrize("value", ["now", "NOW", "now-1d", "now - 1d"])
def test_relative_spellings_are_accepted(value):
    assert isinstance(_to_datetime(value), datetime)


def test_today_resolves_to_midnight_utc():
    assert _to_datetime("today") == _now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def test_absolute_dates_still_parse():
    assert _to_datetime("2026-06-01") == datetime(2026, 6, 1)


def test_a_bare_word_is_still_rejected():
    with pytest.raises(ValueError, match="Not a date or datetime"):
        _to_datetime("yesterday")


# ---------------------------------------------------------------------------
# last_change_at
# ---------------------------------------------------------------------------


def test_last_change_at_is_registered_as_a_datetime():
    field = get_field_registry()["last_change_at"]
    assert field.type == "datetime"
    assert field.sortable


def test_a_listing_with_one_reading_has_never_changed(session: Session):
    _store(session)
    _listing(session, "Azul", [(30.0, _now())])

    changed = Condition(type="condition", field="last_change_at", op="is_not_null")
    assert _titles(session, changed) == []


# ---------------------------------------------------------------------------
# Change windows
# ---------------------------------------------------------------------------


def test_changes_since_a_relative_cutoff(session: Session):
    _store(session)
    _listing(
        session,
        "Recent",
        [(30.0, _now() - timedelta(days=10)), (25.0, _now() - timedelta(hours=3))],
    )
    _listing(
        session,
        "Stale",
        [(30.0, _now() - timedelta(days=40)), (25.0, _now() - timedelta(days=20))],
    )

    assert _titles(session, ChangeWindow(since="-1d")) == ["Recent"]
    assert sorted(_titles(session, ChangeWindow(since="-1mo"))) == ["Recent", "Stale"]


def test_changes_between_last_week_and_now(session: Session):
    _store(session)
    _listing(
        session,
        "ThisWeek",
        [(30.0, _now() - timedelta(days=20)), (25.0, _now() - timedelta(days=2))],
    )
    _listing(
        session,
        "LastMonth",
        [(30.0, _now() - timedelta(days=60)), (25.0, _now() - timedelta(days=20))],
    )
    _listing(
        session,
        "Future",
        [(30.0, _now() - timedelta(days=20)), (25.0, _now() + timedelta(days=1))],
    )

    window = ChangeWindow(since="-1w", until="now")
    assert _titles(session, window) == ["ThisWeek"]


def test_a_window_looks_past_the_most_recent_change(session: Session):
    """A game that also changed today still matches a window that ended yesterday."""
    _store(session)
    _listing(
        session,
        "Azul",
        [
            (30.0, _now() - timedelta(days=60)),
            (25.0, _now() - timedelta(days=25)),
            (20.0, _now()),
        ],
    )

    assert _titles(session, ChangeWindow(since="-1mo", until="-1d")) == ["Azul"]


def test_a_window_without_bounds_asks_for_any_change_ever(session: Session):
    _store(session)
    _listing(session, "Changed", [(30.0, _now() - timedelta(days=9)), (25.0, _now())])
    _listing(session, "Arrived", [(30.0, _now())])

    assert _titles(session, ChangeWindow()) == ["Changed"]


def test_an_arrival_inside_the_window_is_not_a_change(session: Session):
    _store(session)
    _listing(session, "Arrived", [(30.0, _now() - timedelta(hours=2))])

    assert _titles(session, ChangeWindow(since="-1d")) == []


def test_the_bounds_read_the_same_either_way_round(session: Session):
    """A window is a range: which bound was typed first is not the user's problem."""
    _store(session)
    _listing(
        session,
        "Azul",
        [(30.0, _now() - timedelta(days=30)), (25.0, _now() - timedelta(days=3))],
    )
    _listing(session, "Catan", [(40.0, _now() - timedelta(days=30))])

    forwards = ChangeWindow(since="-1w", until="now")
    backwards = ChangeWindow(since="now", until="-1w")
    assert _titles(session, backwards) == _titles(session, forwards) == ["Azul"]


def test_a_window_can_be_open_at_the_start(session: Session):
    _store(session)
    _listing(
        session,
        "Old",
        [(30.0, _now() - timedelta(days=40)), (25.0, _now() - timedelta(days=30))],
    )
    _listing(session, "Fresh", [(30.0, _now() - timedelta(days=2)), (25.0, _now())])

    assert _titles(session, ChangeWindow(until="-1w")) == ["Old"]


def test_both_bounds_include_the_reading_that_sits_on_them(session: Session):
    _store(session)
    moment = _now() - timedelta(days=3)
    _listing(session, "Azul", [(30.0, _now() - timedelta(days=30)), (25.0, moment)])

    on_the_edge = ChangeWindow(since=moment.isoformat(), until=moment.isoformat())
    assert _titles(session, on_the_edge) == ["Azul"]


def test_a_stock_flip_is_a_change_even_at_a_steady_price(session: Session):
    """Stock moves and price moves are both readings, so both land in a window."""
    _store(session)
    product = make_product(session, store_id="s1", external_id="azul", title="Azul")
    for available, recorded_at in [
        (True, _now() - timedelta(days=10)),
        (False, _now() - timedelta(hours=2)),
    ]:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                price=30.0,
                available=available,
                recorded_at=recorded_at,
            )
        )
    session.commit()

    assert _titles(session, ChangeWindow(since="-1d")) == ["Azul"]


def test_a_window_combines_with_other_conditions(session: Session):
    _store(session)
    _listing(session, "Cheap", [(30.0, _now() - timedelta(days=9)), (10.0, _now())])
    _listing(session, "Dear", [(90.0, _now() - timedelta(days=9)), (80.0, _now())])

    node = Group(
        type="group",
        op="and",
        conditions=[
            ChangeWindow(since="-1d"),
            Condition(type="condition", field="price", op="lt", value=50),
        ],
    )
    assert _titles(session, node) == ["Cheap"]


def test_a_window_can_be_negated(session: Session):
    _store(session)
    _listing(session, "Moved", [(30.0, _now() - timedelta(days=9)), (25.0, _now())])
    _listing(session, "Still", [(30.0, _now() - timedelta(days=9))])

    node = Group(type="group", op="not", conditions=[ChangeWindow(since="-1d")])
    assert _titles(session, node) == ["Still"]


def test_hidden_games_stay_out_of_a_window(session: Session):
    _store(session)
    visible = _listing(
        session, "Shown", [(30.0, _now() - timedelta(days=9)), (25.0, _now())]
    )
    buried = _listing(
        session, "Hidden", [(30.0, _now() - timedelta(days=9)), (25.0, _now())]
    )
    game = session.get(Game, buried.game_id)
    game.hidden = True
    session.add(game)
    session.commit()
    assert visible.id is not None

    assert _titles(session, ChangeWindow(since="-1d")) == ["Shown"]


def test_the_total_counts_the_same_games_the_window_returns(session: Session):
    _store(session)
    _listing(session, "Moved", [(30.0, _now() - timedelta(days=9)), (25.0, _now())])
    _listing(session, "Still", [(30.0, _now() - timedelta(days=9))])

    window = ChangeWindow(since="-1d")
    assert count_products(session, filter_node=window) == len(_titles(session, window))


def test_an_unreadable_bound_is_rejected(client, session: Session):
    _store(session)
    _listing(session, "Azul", [(30.0, _now())])

    res = client.post(
        "/api/browse/query",
        json={"filters": {"type": "change_window", "since": "yesterday"}},
    )
    assert res.status_code == 422
    assert "Not a date or datetime" in res.json()["detail"]


def test_a_change_at_any_shop_counts_for_the_game(session: Session):
    """Merged games are one row, so a move at either shop puts it in the window."""
    _store(session)
    _store(session, "s2")
    quiet = _listing(session, "Azul", [(30.0, _now() - timedelta(days=30))])
    other = make_product(
        session,
        store_id="s2",
        external_id="azul-s2",
        title="Azul",
        game=quiet_game(session, quiet),
    )
    for price, recorded_at in [
        (28.0, _now() - timedelta(days=20)),
        (26.0, _now() - timedelta(hours=6)),
    ]:
        session.add(
            PriceSnapshot(product_id=other.id, price=price, recorded_at=recorded_at)
        )
    session.commit()

    assert _titles(session, ChangeWindow(since="-1d")) == ["Azul"]


def test_newest_change_sorts_first(session: Session):
    _store(session)
    _listing(
        session,
        "Older",
        [(30.0, _now() - timedelta(days=9)), (25.0, _now() - timedelta(days=8))],
    )
    _listing(
        session,
        "Newer",
        [(30.0, _now() - timedelta(days=3)), (25.0, _now() - timedelta(days=1))],
    )

    rows = query_products(
        session,
        filter_node=ChangeWindow(),
        sorts=[SortSpec(field="last_change_at", dir="desc")],
    )
    assert [g.title for _, _, g in rows] == ["Newer", "Older"]


def test_an_ignored_reading_does_not_make_a_change(session: Session):
    """A bogus reading is out of every filter, so it cannot invent a change."""
    _store(session)
    product = _listing(session, "Azul", [(30.0, _now() - timedelta(days=2))])
    session.add(
        PriceSnapshot(
            product_id=product.id, price=999.0, recorded_at=_now(), ignored=True
        )
    )
    session.commit()

    assert _titles(session, ChangeWindow()) == []


def test_the_query_endpoint_takes_a_change_window(client, session: Session):
    _store(session)
    _listing(session, "Azul", [(30.0, _now() - timedelta(days=3)), (25.0, _now())])
    _listing(session, "Catan", [(40.0, _now())])

    res = client.post(
        "/api/browse/query",
        json={"filters": {"type": "change_window", "since": "-1d"}},
    )
    assert res.status_code == 200
    assert [i["game"]["title"] for i in res.json()["items"]] == ["Azul"]


def test_the_fields_endpoint_advertises_last_change_at(client):
    names = {f["name"] for f in client.get("/api/browse/fields").json()}
    assert "last_change_at" in names


# ---------------------------------------------------------------------------
# Saved shelves
# ---------------------------------------------------------------------------


def test_a_shelf_keeps_filtering_by_its_window(client, session: Session):
    """A window is a filter node in its own right, so a shelf must rebuild it."""
    _store(session)
    _listing(session, "Moved", [(30.0, _now() - timedelta(days=9)), (25.0, _now())])
    _listing(session, "Still", [(30.0, _now() - timedelta(days=9))])

    created = client.post(
        "/api/shelves/",
        json={
            "name": "Changed today",
            "filters": {"type": "change_window", "since": "-1d"},
        },
    )
    assert created.status_code == 201

    feed = client.get("/api/shelves/preview")
    assert feed.status_code == 200
    shelf = next(s for s in feed.json() if s["shelf"]["name"] == "Changed today")
    assert [i["game"]["title"] for i in shelf["items"]] == ["Moved"]
