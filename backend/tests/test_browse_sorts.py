"""Tests for sort options via the new POST /api/browse/query endpoint."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import BggCache, PriceSnapshot, Product, Store

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
