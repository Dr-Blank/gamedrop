"""Tests for sort options via the new POST /api/browse/query endpoint."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import BggCache, Game, PriceSnapshot, Product, Store

from .factories import make_product


def _store(session: Session, sid: str = "s1"):
    session.add(Store(id=sid, name=sid, type="shopify", base_url=f"https://{sid}.com"))
    session.commit()


def _product(
    session: Session,
    title: str,
    price: float,
    compare_at: float | None = None,
    available: bool = True,
    bgg_id: int | None = None,
    updated_at: datetime | None = None,
) -> Product:
    p = make_product(
        session,
        external_id=title,
        title=title,
        bgg_id=bgg_id,
        updated_at=updated_at or datetime.utcnow(),
    )
    session.add(
        PriceSnapshot(
            product_id=p.id,
            price=price,
            compare_at_price=compare_at,
            available=available,
        )
    )
    session.commit()
    return p


def _bgg_cache(session: Session, bgg_id: int, rating: float, weight: float, rank: int):
    data = json.dumps(
        {
            "bgg_id": bgg_id,
            "name": f"Game {bgg_id}",
            "avg_rating": str(rating),
            "bgg_rating": str(rating),
            "avg_weight": str(weight),
            "rank": rank,
        }
    )
    session.add(BggCache(bgg_id=bgg_id, data=data))
    session.commit()


def _q(filters=None, sorts=None, page=1, limit=48):
    body = {"page": page, "limit": limit}
    if filters:
        body["filters"] = filters
    if sorts:
        body["sorts"] = sorts
    return body


def test_fields_endpoint_returns_sortable_fields(client: TestClient):
    r = client.get("/api/browse/fields")
    assert r.status_code == 200
    sortable = {f["name"] for f in r.json() if f["sortable"]}
    assert {
        "price",
        "discount_pct",
        "discount_abs",
        "bgg_rating",
        "updated_at",
    }.issubset(sortable)


def test_sort_newest(client: TestClient, session: Session):
    _store(session)
    now = datetime.utcnow()
    _product(session, "Old Game", 10.0, updated_at=now - timedelta(days=10))
    _product(session, "New Game", 20.0, updated_at=now)

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "updated_at", "dir": "desc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "New Game"
    assert titles[1] == "Old Game"


def test_sort_discount_pct(client: TestClient, session: Session):
    _store(session)
    _product(session, "Small Discount", 90.0, compare_at=100.0)  # 10%
    _product(session, "Big Discount", 20.0, compare_at=100.0)  # 80%
    _product(session, "No Discount", 50.0)

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "discount_pct", "dir": "desc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "Big Discount"
    assert titles[1] == "Small Discount"


def test_sort_discount_abs(client: TestClient, session: Session):
    _store(session)
    _product(session, "Small Abs", 80.0, compare_at=100.0)  # saves 20
    _product(session, "Big Abs", 10.0, compare_at=200.0)  # saves 190

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "discount_abs", "dir": "desc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "Big Abs"


def test_discount_pct_in_response(client: TestClient, session: Session):
    _store(session)
    _product(session, "Half Off", 50.0, compare_at=100.0)
    _product(session, "No Tag", 50.0)

    r = client.post("/api/browse/query", json=_q())
    assert r.status_code == 200
    by_title = {i["product"]["title"]: i for i in r.json()["items"]}
    assert by_title["Half Off"]["discount_pct"] == pytest.approx(50.0)
    assert by_title["No Tag"]["discount_pct"] is None


def test_sort_bgg_rating(client: TestClient, session: Session):
    _store(session)
    _bgg_cache(session, 1, rating=9.0, weight=3.0, rank=1)
    _bgg_cache(session, 2, rating=6.0, weight=2.0, rank=500)
    _product(session, "Top Rated", 50.0, bgg_id=1)
    _product(session, "Low Rated", 50.0, bgg_id=2)

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "bgg_rating", "dir": "desc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "Top Rated"


def test_sort_price_asc(client: TestClient, session: Session):
    """Cheap games first when sorting price ascending."""
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Pricey", 200.0)

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "price", "dir": "asc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "Cheap"


def test_sort_price_desc(client: TestClient, session: Session):
    """Expensive games first when sorting price descending."""
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Pricey", 200.0)

    r = client.post(
        "/api/browse/query", json=_q(sorts=[{"field": "price", "dir": "desc"}])
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles[0] == "Pricey"


def test_sort_unknown_returns_422(client: TestClient):
    r = client.post(
        "/api/browse/query",
        json={"sorts": [{"field": "nonexistent_field", "dir": "asc"}]},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# store_gap sort — ordering by the price gap between two stores
# ---------------------------------------------------------------------------


def _multi_store_game(session: Session, title: str, offers: dict[str, tuple]):
    """One game listed at several stores: {store_id: (price, available)}."""
    game = Game(title=title)
    session.add(game)
    session.flush()
    for store_id, (price, available) in offers.items():
        p = make_product(
            session,
            store_id=store_id,
            external_id=f"{store_id}-{title}",
            title=title,
            game=game,
        )
        session.add(PriceSnapshot(product_id=p.id, price=price, available=available))
    session.commit()
    return game


def _gap_sort(**kwargs):
    return [{"type": "store_gap", "store_a": "s1", **kwargs}]


def _titles(client: TestClient, sorts, **kwargs):
    r = client.post("/api/browse/query", json=_q(sorts=sorts, **kwargs))
    assert r.status_code == 200, r.text
    return [i["game"]["title"] for i in r.json()["items"]]


def test_store_gap_sort_orders_by_saving(client: TestClient, session: Session):
    _store(session, "s1")
    _store(session, "s2")
    _multi_store_game(session, "BigSaving", {"s1": (700.0, True), "s2": (1000.0, True)})
    _multi_store_game(
        session, "SmallSaving", {"s1": (950.0, True), "s2": (1000.0, True)}
    )
    _multi_store_game(session, "Dearer", {"s1": (1100.0, True), "s2": (1000.0, True)})

    asc = _titles(client, _gap_sort(store_b="s2", dir="asc"))
    assert asc == ["BigSaving", "SmallSaving", "Dearer"]
    assert _titles(client, _gap_sort(store_b="s2", dir="desc")) == asc[::-1]


def test_store_gap_sort_pct_mode_ranks_by_share_not_amount(
    client: TestClient, session: Session
):
    _store(session, "s1")
    _store(session, "s2")
    # 100 off 200 is a deeper cut than 150 off 2000.
    _multi_store_game(session, "Half", {"s1": (100.0, True), "s2": (200.0, True)})
    _multi_store_game(session, "Sliver", {"s1": (1850.0, True), "s2": (2000.0, True)})

    assert _titles(client, _gap_sort(store_b="s2", mode="pct", dir="asc")) == [
        "Half",
        "Sliver",
    ]


def test_store_gap_sort_wildcard_compares_cheapest_other_store(
    client: TestClient, session: Session
):
    """`*` measures against whichever other store is cheapest, not a named one."""
    for sid in ("s1", "s2", "s3"):
        _store(session, sid)
    _multi_store_game(
        session,
        "BeatsBoth",
        {"s1": (500.0, True), "s2": (900.0, True), "s3": (800.0, True)},
    )
    _multi_store_game(
        session,
        "BeatsOne",
        {"s1": (850.0, True), "s2": (900.0, True), "s3": (800.0, True)},
    )

    assert _titles(client, _gap_sort(store_b="*", dir="asc")) == [
        "BeatsBoth",
        "BeatsOne",
    ]


def test_store_gap_sort_in_stock_only_skips_unbuyable_offer(
    client: TestClient, session: Session
):
    _store(session, "s1")
    _store(session, "s2")
    _store(session, "s3")
    # s2 is cheaper but out of stock, so only s3 counts as a gap to beat.
    _multi_store_game(
        session,
        "OnlyBuyable",
        {"s1": (700.0, True), "s2": (100.0, False), "s3": (1000.0, True)},
    )
    _multi_store_game(session, "Plain", {"s1": (950.0, True), "s3": (1000.0, True)})

    assert _titles(client, _gap_sort(store_b="*", stock="in_stock", dir="asc")) == [
        "OnlyBuyable",
        "Plain",
    ]
    # With stock ignored, the out-of-stock ₹100 offer makes the same game dearest.
    assert _titles(client, _gap_sort(store_b="*", stock="any", dir="asc")) == [
        "Plain",
        "OnlyBuyable",
    ]


def test_store_gap_sort_ranks_games_missing_a_store_last(
    client: TestClient, session: Session
):
    _store(session, "s1")
    _store(session, "s2")
    _multi_store_game(session, "Both", {"s1": (700.0, True), "s2": (1000.0, True)})
    _multi_store_game(session, "OnlyOne", {"s1": (10.0, True)})

    assert _titles(client, _gap_sort(store_b="s2", dir="asc")) == ["Both", "OnlyOne"]


def test_store_gap_sort_does_not_duplicate_a_double_listing(
    client: TestClient, session: Session
):
    """A shop listing the same game twice still yields one card."""
    _store(session, "s1")
    _store(session, "s2")
    game = _multi_store_game(
        session, "Twice", {"s1": (700.0, True), "s2": (1000.0, True)}
    )
    extra = make_product(
        session, store_id="s1", external_id="s1-dupe", title="Twice", game=game
    )
    session.add(PriceSnapshot(product_id=extra.id, price=720.0, available=True))
    session.commit()

    assert _titles(client, _gap_sort(store_b="s2", dir="asc")) == ["Twice"]


def test_store_gap_sort_unknown_store_returns_no_order_error(
    client: TestClient, session: Session
):
    """An unknown store is an empty comparison, not a 422."""
    _store(session, "s1")
    _product(session, "Lonely", 10.0)
    r = client.post("/api/browse/query", json=_q(sorts=_gap_sort(store_b="nope")))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Paging over games — a merged game must not appear on two pages
# ---------------------------------------------------------------------------


def test_merged_game_not_repeated_across_pages(client: TestClient, session: Session):
    _store(session, "s1")
    _store(session, "s2")
    for i in range(4):
        _multi_store_game(
            session, f"Game {i}", {"s1": (100.0 + i, True), "s2": (200.0 + i, True)}
        )

    seen = []
    for page in range(1, 4):
        r = client.post(
            "/api/browse/query",
            json=_q(sorts=[{"field": "title", "dir": "asc"}], page=page, limit=2),
        )
        assert r.status_code == 200
        seen += [i["game"]["title"] for i in r.json()["items"]]

    assert seen == ["Game 0", "Game 1", "Game 2", "Game 3"]


def test_page_is_full_when_games_are_merged(client: TestClient, session: Session):
    """A page holds `limit` games however many listings each of them has."""
    _store(session, "s1")
    _store(session, "s2")
    for i in range(6):
        _multi_store_game(
            session, f"Game {i}", {"s1": (100.0 + i, True), "s2": (200.0 + i, True)}
        )

    r = client.post(
        "/api/browse/query",
        json=_q(sorts=[{"field": "title", "dir": "asc"}], page=1, limit=4),
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 4
    assert r.json()["total"] == 6


def test_store_gap_sort_rejects_wildcard_on_the_measured_side(client: TestClient):
    r = client.post(
        "/api/browse/query", json=_q(sorts=_gap_sort(store_a="*", store_b="s2"))
    )
    assert r.status_code == 422


def test_paging_is_stable_when_the_sort_ties(client: TestClient, session: Session):
    """Games sharing a price still page without repeats or gaps."""
    _store(session, "s1")
    for i in range(6):
        _product(session, f"Tied {i}", 500.0)

    seen = []
    for page in range(1, 4):
        r = client.post(
            "/api/browse/query",
            json=_q(sorts=[{"field": "price", "dir": "asc"}], page=page, limit=2),
        )
        assert r.status_code == 200
        seen += [i["game"]["title"] for i in r.json()["items"]]

    assert sorted(seen) == [f"Tied {i}" for i in range(6)]
