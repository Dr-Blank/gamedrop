"""The change timeline: every price and stock move across shops, newest first."""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.models import Game, PriceSnapshot

from .factories import make_product, make_store, watch


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _listing(session: Session, store_id: str, title: str, readings, game=None):
    """A listing with (price, available, hours_ago) readings, oldest first."""
    product = make_product(
        session,
        store_id=store_id,
        title=title,
        external_id=f"{store_id}-{title}",
        game=game,
    )
    for price, available, hours_ago in readings:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                price=price,
                available=available,
                recorded_at=_now() - timedelta(hours=hours_ago),
            )
        )
    session.commit()
    return product


def _setup(session: Session):
    make_store(session, "a")
    make_store(session, "b")
    ark = _listing(
        session, "a", "Ark", [(100, True, 50), (100, True, 40), (80, True, 30)]
    )
    game = session.get(Game, ark.game_id)
    _listing(
        session, "b", "Ark", [(90, True, 50), (90, False, 20), (90, True, 10)], game
    )
    _listing(session, "b", "Cascadia", [(50, True, 5)])
    return ark


def _get(client, **params):
    r = client.get("/api/timeline/events", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _kinds(body):
    return [(e["store_id"], e["kind"]) for e in body["events"]]


def test_lists_every_change_newest_first(client, session):
    _setup(session)
    body = _get(client)
    assert _kinds(body) == [
        ("b", "listed"),
        ("b", "restock"),
        ("b", "oos"),
        ("a", "drop"),
        ("b", "listed"),
        ("a", "listed"),
    ]


def test_repeated_readings_are_not_events(client, session):
    _setup(session)
    prices = [
        (e["store_id"], e["prev_price"], e["price"]) for e in _get(client)["events"]
    ]
    assert ("a", 100, 100) not in prices
    assert ("a", 100, 80) in prices


def test_narrows_to_chosen_stores_and_kinds(client, session):
    _setup(session)
    assert _kinds(_get(client, stores="a", kinds="drop,rise")) == [("a", "drop")]
    assert _kinds(_get(client, stores="b", kinds="oos,restock")) == [
        ("b", "restock"),
        ("b", "oos"),
    ]


def test_window_bounds_are_relative(client, session):
    _setup(session)
    assert _kinds(_get(client, since="-1d")) == [
        ("b", "listed"),
        ("b", "restock"),
        ("b", "oos"),
    ]


def test_small_price_moves_drop_out_but_stock_moves_stay(client, session):
    _setup(session)
    body = _get(client, min_pct=25, kinds="drop,restock")
    assert _kinds(body) == [("b", "restock")]
    assert _kinds(_get(client, min_pct=20, kinds="drop")) == [("a", "drop")]


def test_watchlist_only(client, session):
    ark = _setup(session)
    watch(session, ark)
    game_ids = {e["game_id"] for e in _get(client, watchlist=True)["events"]}
    assert game_ids == {ark.game_id}


def test_hidden_games_are_left_out(client, session):
    ark = _setup(session)
    session.get(Game, ark.game_id).hidden = True
    session.commit()
    assert _kinds(_get(client)) == [("b", "listed")]


def test_ignored_readings_are_not_events(client, session):
    ark = _setup(session)
    snap = session.exec(
        select(PriceSnapshot).where(
            PriceSnapshot.product_id == ark.id, PriceSnapshot.price == 80
        )
    ).one()
    snap.ignored = True
    session.commit()
    assert ("a", "drop") not in _kinds(_get(client))


def test_pages_with_a_cursor_without_gaps_or_repeats(client, session):
    _setup(session)
    everything = [e["snapshot_id"] for e in _get(client)["events"]]
    seen, cursor = [], None
    while True:
        body = _get(client, limit=2, **({"before": cursor} if cursor else {}))
        seen += [e["snapshot_id"] for e in body["events"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == everything


def test_each_game_carries_every_shops_history(client, session):
    ark = _setup(session)
    games = _get(client, stores="a")["games"]
    series = games[str(ark.game_id)]["series"]
    assert {s["store_id"] for s in series} == {"a", "b"}
    # The standing 100 is folded into one reading; the latest is always kept.
    a = next(s for s in series if s["store_id"] == "a")
    assert [h["price"] for h in a["history"]] == [100, 80]


def test_rejects_unknown_kinds_and_bad_cursors(client, session):
    assert (
        client.get("/api/timeline/events", params={"kinds": "nope"}).status_code == 422
    )
    assert client.get("/api/timeline/events", params={"before": "x"}).status_code == 422


def test_caught_up_line_starts_unset(client):
    assert client.get("/api/timeline/seen").json() == {"seen_at": None}


def test_caught_up_line_moves_forward_only(client):
    later, earlier = "2026-10-16T10:00:00", "2026-10-15T10:00:00"
    assert client.put("/api/timeline/seen", json={"seen_at": later}).status_code == 200
    client.put("/api/timeline/seen", json={"seen_at": earlier})
    assert client.get("/api/timeline/seen").json() == {"seen_at": later}


def test_caught_up_line_takes_a_zoned_time_as_utc(client):
    client.put("/api/timeline/seen", json={"seen_at": "2026-10-16T15:30:00+05:30"})
    assert client.get("/api/timeline/seen").json() == {"seen_at": "2026-10-16T10:00:00"}


def test_caught_up_defaults_to_now(client):
    body = client.put("/api/timeline/seen", json={}).json()
    assert datetime.fromisoformat(body["seen_at"]) > _now() - timedelta(minutes=1)


def test_chart_enters_at_the_price_standing_before_it(client, session):
    make_store(session, "a")
    old = _listing(session, "a", "Old", [(70, True, 24 * 200), (60, True, 24 * 100)])
    _listing(session, "a", "Old2", [(10, True, 1)])
    session.add(
        PriceSnapshot(
            product_id=old.id, price=50, recorded_at=_now() - timedelta(hours=2)
        )
    )
    session.commit()
    body = _get(client, since="-1d")
    a = body["games"][str(old.game_id)]["series"][0]
    # The 70 has aged out; the chart starts from the 60 in force before it.
    assert [h["price"] for h in a["history"]] == [60, 50]


def test_variants_are_compared_only_with_themselves(client, session):
    make_store(session, "a")
    product = make_product(session, store_id="a", title="Ark")
    for variant, price, hours_ago in [("de", 100, 3), ("en", 120, 2), ("de", 100, 1)]:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                variant_id=variant,
                price=price,
                recorded_at=_now() - timedelta(hours=hours_ago),
            )
        )
    session.commit()
    assert _kinds(_get(client)) == [("a", "listed"), ("a", "listed")]


def test_a_move_off_a_zero_price_survives_the_size_filter(client, session):
    make_store(session, "a")
    _listing(session, "a", "Free", [(0, True, 3), (50, True, 1)])
    assert _kinds(_get(client, min_pct=10, kinds="rise")) == [("a", "rise")]


def test_watchlist_combines_with_kinds(client, session):
    ark = _setup(session)
    watch(session, ark)
    assert _kinds(_get(client, watchlist=True, kinds="drop,restock")) == [
        ("b", "restock"),
        ("a", "drop"),
    ]
