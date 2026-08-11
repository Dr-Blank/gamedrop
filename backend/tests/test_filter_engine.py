"""
Comprehensive tests for the filter engine.

Covers:
- All operators per field type (eq/ne/gt/gte/lt/lte/contains/starts_with/
  ends_with/in/not_in/is_null/is_not_null)
- AND / OR / NOT groups
- Nested group combinations
- Multi-sort priority chains (available desc → price asc → discount desc)
- Auto-discovery (new Product/PriceSnapshot fields appear in registry)
- /api/browse/query POST endpoint (integration)
- /api/browse/fields GET endpoint (introspection)
- /api/browse/ GET still works (backward compat)
- Error paths (unknown field, bad operator, NOT with > 1 child)
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.filter_engine import (
    Condition,
    Group,
    SortSpec,
    _infer_type,
    apply_filter,
    apply_sorts,
    auto_register_model,
    build_field_registry,
    describe_fields,
)
from app.models import BggCache, Game, PriceSnapshot, Product, Store, WatchlistItem
from app.repositories.catalog import (
    count_products,
    get_field_registry,
    query_products,
)

from .factories import make_product

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _store(session: Session, sid: str = "s1", name: str = "Store 1"):
    session.add(Store(id=sid, name=name, type="shopify", base_url=f"https://{sid}.com"))
    session.commit()


def _product(
    session: Session,
    title: str,
    price: float,
    *,
    sid: str = "s1",
    compare_at: float | None = None,
    available: bool = True,
    bgg_id: int | None = None,
    updated_at: datetime | None = None,
    hidden: bool = False,
) -> Product:
    p = make_product(
        session,
        store_id=sid,
        external_id=title,
        title=title,
        bgg_id=bgg_id,
        updated_at=updated_at or datetime.utcnow(),
    )
    if hidden:
        game = session.get(Game, p.game_id)
        game.hidden = True
        session.add(game)
        session.commit()
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


def _bgg(
    session: Session,
    bgg_id: int,
    rating: float = 7.0,
    weight: float = 2.0,
    rank: int = 100,
):
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


# ---------------------------------------------------------------------------
# Unit: _infer_type
# ---------------------------------------------------------------------------


def test_infer_type_primitives():
    assert _infer_type(str) == "str"
    assert _infer_type(int) == "int"
    assert _infer_type(float) == "float"
    assert _infer_type(bool) == "bool"
    assert _infer_type(datetime) == "datetime"


def test_infer_type_optional():
    assert _infer_type(str | None) == "str"
    assert _infer_type(float | None) == "float"
    assert _infer_type(int | None) == "int"


def test_infer_type_bool_not_int():
    # bool must resolve before int (bool is subclass of int in Python)
    assert _infer_type(bool) == "bool"
    assert _infer_type(bool | None) == "bool"


# ---------------------------------------------------------------------------
# Unit: auto_register_model
# ---------------------------------------------------------------------------


def test_auto_register_product_fields():
    fields = auto_register_model(Product)
    assert "store_id" in fields
    assert "game_id" in fields
    assert "updated_at" in fields
    assert fields["updated_at"].type == "datetime"


def test_auto_register_game_fields():
    """Name, BGG link and hidden are the game's, so they register from Game."""
    fields = auto_register_model(Game)
    assert fields["title"].type == "str"
    assert fields["hidden"].type == "bool"
    assert fields["bgg_id"].type == "int"


def test_auto_register_pricesnap_fields():
    fields = auto_register_model(PriceSnapshot)
    assert "price" in fields
    assert "compare_at_price" in fields
    assert "available" in fields
    assert fields["price"].type == "float"
    assert fields["available"].type == "bool"


def test_auto_register_skip():
    fields = auto_register_model(Product, skip={"title", "hidden"})
    assert "title" not in fields
    assert "hidden" not in fields
    assert "store_id" in fields


# ---------------------------------------------------------------------------
# Unit: build_field_registry / describe_fields
# ---------------------------------------------------------------------------


def test_registry_contains_all_sources():
    from app.repositories.catalog import _bgg_subq, _first_seen_subq

    reg = build_field_registry(_bgg_subq(), _first_seen_subq())
    # Product
    assert "title" in reg
    assert "store_id" in reg
    # PriceSnapshot
    assert "price" in reg
    assert "available" in reg
    # BGG
    assert "bgg_rating" in reg
    assert "avg_weight" in reg
    assert "bgg_rank" in reg
    # Computed
    assert "discount_pct" in reg
    assert "discount_abs" in reg
    assert "first_seen" in reg


def test_describe_fields_shape():
    reg = get_field_registry()
    fields = describe_fields(reg)
    assert isinstance(fields, list)
    assert len(fields) > 5
    names = {f["name"] for f in fields}
    assert "price" in names
    assert "title" in names
    price_field = next(f for f in fields if f["name"] == "price")
    assert "gte" in price_field["ops"]
    assert "lte" in price_field["ops"]
    assert "contains" not in price_field["ops"]
    title_field = next(f for f in fields if f["name"] == "title")
    assert "contains" in title_field["ops"]
    assert "starts_with" in title_field["ops"]


# ---------------------------------------------------------------------------
# Unit: apply_filter — leaf conditions
# ---------------------------------------------------------------------------


def _exec(session: Session, filter_node, **kwargs):
    """Run query_products with a single filter node."""
    rows = query_products(session, filter_node=filter_node, **kwargs)
    return [g.title for _, _, g in rows]


def test_filter_eq_str(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    result = _exec(session, Condition(field="title", op="eq", value="Catan"))
    assert result == ["Catan"]


def test_filter_ne_str(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    result = _exec(session, Condition(field="title", op="ne", value="Catan"))
    assert "Pandemic" in result
    assert "Catan" not in result


def test_filter_contains(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    _product(session, "Catacombs", 40.0)
    result = _exec(session, Condition(field="title", op="contains", value="cat"))
    assert set(result) == {"Catan", "Catacombs"}


def test_filter_starts_with(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    _product(session, "Catacombs", 40.0)
    result = _exec(session, Condition(field="title", op="starts_with", value="Cat"))
    assert set(result) == {"Catan", "Catacombs"}


def test_filter_ends_with(session: Session):
    _store(session)
    _product(session, "Pandemic Legacy", 70.0)
    _product(session, "Catan", 30.0)
    result = _exec(session, Condition(field="title", op="ends_with", value="Legacy"))
    assert result == ["Pandemic Legacy"]


def test_filter_in_str(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    _product(session, "Azul", 20.0)
    result = _exec(session, Condition(field="title", op="in", value=["Catan", "Azul"]))
    assert set(result) == {"Catan", "Azul"}


def test_filter_not_in_str(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    _product(session, "Azul", 20.0)
    result = _exec(
        session, Condition(field="title", op="not_in", value=["Catan", "Azul"])
    )
    assert result == ["Pandemic"]


def test_filter_gt_float(session: Session):
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Mid", 30.0)
    _product(session, "Pricey", 60.0)
    result = _exec(session, Condition(field="price", op="gt", value=25.0))
    assert set(result) == {"Mid", "Pricey"}


def test_filter_gte_float(session: Session):
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Exact", 30.0)
    _product(session, "Pricey", 60.0)
    result = _exec(session, Condition(field="price", op="gte", value=30.0))
    assert set(result) == {"Exact", "Pricey"}


def test_filter_lt_float(session: Session):
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Mid", 30.0)
    result = _exec(session, Condition(field="price", op="lt", value=30.0))
    assert result == ["Cheap"]


def test_filter_lte_float(session: Session):
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Exact", 30.0)
    _product(session, "Pricey", 60.0)
    result = _exec(session, Condition(field="price", op="lte", value=30.0))
    assert set(result) == {"Cheap", "Exact"}


def test_filter_eq_bool_available(session: Session):
    _store(session)
    _product(session, "InStock", 20.0, available=True)
    _product(session, "OutOfStock", 20.0, available=False)
    result = _exec(session, Condition(field="available", op="eq", value=True))
    assert result == ["InStock"]


def test_filter_eq_bool_false(session: Session):
    _store(session)
    _product(session, "InStock", 20.0, available=True)
    _product(session, "OutOfStock", 20.0, available=False)
    result = _exec(session, Condition(field="available", op="eq", value=False))
    assert result == ["OutOfStock"]


def test_filter_is_null_bgg(session: Session):
    _store(session)
    _product(session, "NoBgg", 20.0)
    _product(session, "HasBgg", 30.0, bgg_id=1)
    result = _exec(session, Condition(field="bgg_id", op="is_null"))
    assert result == ["NoBgg"]


def test_filter_is_not_null_bgg(session: Session):
    _store(session)
    _product(session, "NoBgg", 20.0)
    _product(session, "HasBgg", 30.0, bgg_id=1)
    result = _exec(session, Condition(field="bgg_id", op="is_not_null"))
    assert result == ["HasBgg"]


def test_filter_in_numeric(session: Session):
    _store(session)
    _product(session, "A", 10.0)
    _product(session, "B", 20.0)
    _product(session, "C", 30.0)
    result = _exec(session, Condition(field="price", op="in", value=[10.0, 30.0]))
    assert set(result) == {"A", "C"}


def test_filter_store_id_eq(session: Session):
    _store(session, "s1")
    _store(session, "s2")
    _product(session, "FromS1", 10.0, sid="s1")
    _product(session, "FromS2", 10.0, sid="s2")
    result = _exec(session, Condition(field="store_id", op="eq", value="s1"))
    assert result == ["FromS1"]


def test_filter_store_id_in(session: Session):
    _store(session, "s1")
    _store(session, "s2")
    _store(session, "s3")
    _product(session, "A", 10.0, sid="s1")
    _product(session, "B", 10.0, sid="s2")
    _product(session, "C", 10.0, sid="s3")
    result = _exec(session, Condition(field="store_id", op="in", value=["s1", "s3"]))
    assert set(result) == {"A", "C"}


def test_filter_ne_float(session: Session):
    _store(session)
    _product(session, "Exact", 30.0)
    _product(session, "Other", 50.0)
    result = _exec(session, Condition(field="price", op="ne", value=30.0))
    assert result == ["Other"]


# ---------------------------------------------------------------------------
# Unit: apply_filter — groups (AND / OR / NOT)
# ---------------------------------------------------------------------------


def test_and_group(session: Session):
    _store(session)
    _product(session, "Cheap InStock", 10.0, available=True)
    _product(session, "Cheap OutOfStock", 10.0, available=False)
    _product(session, "Pricey InStock", 80.0, available=True)

    node = Group(
        op="and",
        conditions=[
            Condition(field="price", op="lte", value=20.0),
            Condition(field="available", op="eq", value=True),
        ],
    )
    result = _exec(session, node)
    assert result == ["Cheap InStock"]


def test_or_group(session: Session):
    _store(session)
    _product(session, "Cheap", 5.0)
    _product(session, "Mid", 40.0)
    _product(session, "Pricey", 100.0)

    node = Group(
        op="or",
        conditions=[
            Condition(field="price", op="lte", value=10.0),
            Condition(field="price", op="gte", value=90.0),
        ],
    )
    result = _exec(session, node)
    assert set(result) == {"Cheap", "Pricey"}


def test_not_group(session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)

    node = Group(
        op="not",
        conditions=[
            Condition(field="title", op="eq", value="Catan"),
        ],
    )
    result = _exec(session, node)
    assert result == ["Pandemic"]


def test_not_group_wrong_child_count():
    from app.repositories.catalog import _bgg_subq, _first_seen_subq

    reg = build_field_registry(_bgg_subq(), _first_seen_subq())
    node = Group(
        op="not",
        conditions=[
            Condition(field="title", op="eq", value="A"),
            Condition(field="title", op="eq", value="B"),
        ],
    )
    with pytest.raises(ValueError, match="NOT group must have exactly 1"):
        apply_filter(node, reg)


def test_nested_group_and_or(session: Session):
    """(available=True AND price < 50) OR title contains 'Legacy'"""
    _store(session)
    _product(session, "Cheap InStock", 20.0, available=True)
    _product(session, "Pricey InStock", 80.0, available=True)
    _product(session, "Cheap OutOfStock", 20.0, available=False)
    _product(session, "Pandemic Legacy", 60.0, available=False)

    node = Group(
        op="or",
        conditions=[
            Group(
                op="and",
                conditions=[
                    Condition(field="available", op="eq", value=True),
                    Condition(field="price", op="lt", value=50.0),
                ],
            ),
            Condition(field="title", op="contains", value="Legacy"),
        ],
    )
    result = _exec(session, node)
    assert set(result) == {"Cheap InStock", "Pandemic Legacy"}


def test_nested_group_and_not(session: Session):
    """available=True AND NOT title='Catan'"""
    _store(session)
    _product(session, "Catan", 30.0, available=True)
    _product(session, "Pandemic", 50.0, available=True)
    _product(session, "Azul", 20.0, available=False)

    node = Group(
        op="and",
        conditions=[
            Condition(field="available", op="eq", value=True),
            Group(
                op="not",
                conditions=[
                    Condition(field="title", op="eq", value="Catan"),
                ],
            ),
        ],
    )
    result = _exec(session, node)
    assert result == ["Pandemic"]


def test_deeply_nested_group(session: Session):
    """(A AND (B OR C)) AND NOT D"""
    _store(session)
    _product(
        session, "Match", 25.0, available=True
    )  # price 10-30, available, not title=X
    _product(session, "TooExpensive", 60.0, available=True)
    _product(session, "OutOfStock", 25.0, available=False)
    _product(session, "Exclude", 25.0, available=True)  # will be excluded by NOT

    node = Group(
        op="and",
        conditions=[
            Condition(field="available", op="eq", value=True),
            Group(
                op="or",
                conditions=[
                    Condition(field="price", op="gte", value=10.0),
                    Condition(field="title", op="contains", value="special"),
                ],
            ),
            Group(
                op="not",
                conditions=[
                    Condition(field="title", op="eq", value="Exclude"),
                ],
            ),
        ],
    )
    result = _exec(session, node)
    assert "Match" in result
    assert "TooExpensive" in result
    assert "OutOfStock" not in result
    assert "Exclude" not in result


# ---------------------------------------------------------------------------
# Unit: apply_sorts — multi-sort priority
# ---------------------------------------------------------------------------


def test_sort_single_price_asc(session: Session):
    _store(session)
    _product(session, "C", 30.0)
    _product(session, "A", 10.0)
    _product(session, "B", 20.0)
    rows = query_products(session, sorts=[SortSpec(field="price", dir="asc")])
    prices = [s.price for _, s, _ in rows]
    assert prices == sorted(prices)


def test_sort_single_price_desc(session: Session):
    _store(session)
    _product(session, "C", 30.0)
    _product(session, "A", 10.0)
    _product(session, "B", 20.0)
    rows = query_products(session, sorts=[SortSpec(field="price", dir="desc")])
    prices = [s.price for _, s, _ in rows]
    assert prices == sorted(prices, reverse=True)


def test_sort_multi_available_then_price(session: Session):
    """Primary: available desc. Secondary: price asc."""
    _store(session)
    _product(session, "OutPricey", 80.0, available=False)
    _product(session, "OutCheap", 5.0, available=False)
    _product(session, "InPricey", 60.0, available=True)
    _product(session, "InCheap", 15.0, available=True)

    rows = query_products(
        session,
        sorts=[
            SortSpec(field="available", dir="desc"),
            SortSpec(field="price", dir="asc"),
        ],
    )
    titles = [g.title for _, _, g in rows]
    # InStock first, cheapest among each group first
    in_stock = [t for t in titles if t.startswith("In")]
    out_stock = [t for t in titles if t.startswith("Out")]
    # all InStock appear before any OutOfStock
    last_in = max(titles.index(t) for t in in_stock)
    first_out = min(titles.index(t) for t in out_stock)
    assert last_in < first_out
    # within in-stock: InCheap before InPricey
    assert titles.index("InCheap") < titles.index("InPricey")
    # within out-of-stock: OutCheap before OutPricey
    assert titles.index("OutCheap") < titles.index("OutPricey")


def test_sort_multi_three_levels(session: Session):
    """available desc → price asc → discount_pct desc"""
    _store(session)
    # Both in-stock, same price, different discounts
    _product(session, "InHighDiscount", 50.0, available=True, compare_at=100.0)
    _product(session, "InLowDiscount", 50.0, available=True, compare_at=60.0)
    _product(session, "OutGame", 10.0, available=False)

    rows = query_products(
        session,
        sorts=[
            SortSpec(field="available", dir="desc"),
            SortSpec(field="price", dir="asc"),
            SortSpec(field="discount_pct", dir="desc"),
        ],
    )
    titles = [g.title for _, _, g in rows]
    assert titles[-1] == "OutGame"
    assert titles.index("InHighDiscount") < titles.index("InLowDiscount")


def test_sort_updated_at_desc(session: Session):
    _store(session)
    now = datetime.utcnow()
    _product(session, "Old", 10.0, updated_at=now - timedelta(days=5))
    _product(session, "New", 10.0, updated_at=now)
    rows = query_products(session, sorts=[SortSpec(field="updated_at", dir="desc")])
    titles = [g.title for _, _, g in rows]
    assert titles[0] == "New"


def test_sort_title_asc(session: Session):
    _store(session)
    _product(session, "Zorro", 10.0)
    _product(session, "Azul", 10.0)
    _product(session, "Meeple", 10.0)
    rows = query_products(session, sorts=[SortSpec(field="title", dir="asc")])
    titles = [g.title for _, _, g in rows]
    assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# Unit: error paths
# ---------------------------------------------------------------------------


def test_unknown_filter_field():
    from app.repositories.catalog import _bgg_subq, _first_seen_subq

    reg = build_field_registry(_bgg_subq(), _first_seen_subq())
    node = Condition(field="nonexistent_xyz", op="eq", value="foo")
    with pytest.raises(ValueError, match="Unknown filter field"):
        apply_filter(node, reg)


def test_bad_operator_for_type():
    from app.repositories.catalog import _bgg_subq, _first_seen_subq

    reg = build_field_registry(_bgg_subq(), _first_seen_subq())
    # "contains" is not valid for float field
    node = Condition(field="price", op="contains", value="foo")
    with pytest.raises(ValueError, match="not allowed"):
        apply_filter(node, reg)


def test_unknown_sort_field():
    from sqlmodel import select

    from app.models import Product
    from app.repositories.catalog import _bgg_subq, _first_seen_subq

    reg = build_field_registry(_bgg_subq(), _first_seen_subq())
    stmt = select(Product)
    with pytest.raises(ValueError, match="Unknown sort field"):
        apply_sorts(stmt, [SortSpec(field="nonexistent_xyz")], reg)


# ---------------------------------------------------------------------------
# Integration: POST /api/browse/query
# ---------------------------------------------------------------------------


def test_post_query_no_filters(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    r = client.post("/api/browse/query", json={})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


def test_post_query_eq_filter(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "title",
                "op": "eq",
                "value": "Catan",
            }
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["product"]["title"] == "Catan"
    assert data["total"] == 1


def test_post_query_price_range(client: TestClient, session: Session):
    _store(session)
    _product(session, "Cheap", 10.0)
    _product(session, "Mid", 35.0)
    _product(session, "Pricey", 80.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "group",
                "op": "and",
                "conditions": [
                    {"type": "condition", "field": "price", "op": "gte", "value": 20.0},
                    {"type": "condition", "field": "price", "op": "lte", "value": 50.0},
                ],
            }
        },
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles == ["Mid"]


def test_post_query_or_filter(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 10.0)
    _product(session, "Pandemic", 50.0)
    _product(session, "Azul", 80.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "group",
                "op": "or",
                "conditions": [
                    {
                        "type": "condition",
                        "field": "title",
                        "op": "eq",
                        "value": "Catan",
                    },
                    {"type": "condition", "field": "price", "op": "gte", "value": 70.0},
                ],
            }
        },
    )
    assert r.status_code == 200
    titles = {i["product"]["title"] for i in r.json()["items"]}
    assert titles == {"Catan", "Azul"}


def test_post_query_not_filter(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    _product(session, "Pandemic", 50.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "group",
                "op": "not",
                "conditions": [
                    {
                        "type": "condition",
                        "field": "title",
                        "op": "eq",
                        "value": "Catan",
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "Pandemic" in titles
    assert "Catan" not in titles


def test_post_query_contains_filter(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan Seafarers", 50.0)
    _product(session, "Pandemic", 40.0)
    _product(session, "Catan Base", 30.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "title",
                "op": "contains",
                "value": "Catan",
            }
        },
    )
    assert r.status_code == 200
    titles = {i["product"]["title"] for i in r.json()["items"]}
    assert titles == {"Catan Seafarers", "Catan Base"}


def test_post_query_in_filter(client: TestClient, session: Session):
    _store(session, "s1")
    _store(session, "s2")
    _store(session, "s3")
    _product(session, "A", 10.0, sid="s1")
    _product(session, "B", 10.0, sid="s2")
    _product(session, "C", 10.0, sid="s3")
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "store_id",
                "op": "in",
                "value": ["s1", "s3"],
            }
        },
    )
    assert r.status_code == 200
    titles = {i["product"]["title"] for i in r.json()["items"]}
    assert titles == {"A", "C"}


def test_post_query_is_null_bgg(client: TestClient, session: Session):
    _store(session)
    _product(session, "NoBgg", 20.0)
    _product(session, "HasBgg", 30.0, bgg_id=42)
    r = client.post(
        "/api/browse/query",
        json={"filters": {"type": "condition", "field": "bgg_id", "op": "is_null"}},
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles == ["NoBgg"]


def test_post_query_available_eq_false(client: TestClient, session: Session):
    _store(session)
    _product(session, "InStock", 20.0, available=True)
    _product(session, "OutOfStock", 20.0, available=False)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "available",
                "op": "eq",
                "value": False,
            }
        },
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert titles == ["OutOfStock"]


def test_post_query_multi_sort(client: TestClient, session: Session):
    """available desc → price asc via API."""
    _store(session)
    _product(session, "InCheap", 10.0, available=True)
    _product(session, "InPricey", 80.0, available=True)
    _product(session, "OutCheap", 5.0, available=False)
    r = client.post(
        "/api/browse/query",
        json={
            "sorts": [
                {"field": "available", "dir": "desc"},
                {"field": "price", "dir": "asc"},
            ]
        },
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    # InStock first
    assert titles.index("InCheap") < titles.index("OutCheap")
    assert titles.index("InPricey") < titles.index("OutCheap")
    # Among in-stock, cheapest first
    assert titles.index("InCheap") < titles.index("InPricey")


def test_post_query_nested_complex(client: TestClient, session: Session):
    """(available AND price<50) OR title='Pandemic Legacy'"""
    _store(session)
    _product(session, "Cheap InStock", 20.0, available=True)
    _product(session, "Pricey InStock", 90.0, available=True)
    _product(session, "Pandemic Legacy", 65.0, available=False)
    _product(session, "Random Out", 30.0, available=False)

    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "group",
                "op": "or",
                "conditions": [
                    {
                        "type": "group",
                        "op": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "available",
                                "op": "eq",
                                "value": True,
                            },
                            {
                                "type": "condition",
                                "field": "price",
                                "op": "lt",
                                "value": 50.0,
                            },
                        ],
                    },
                    {
                        "type": "condition",
                        "field": "title",
                        "op": "eq",
                        "value": "Pandemic Legacy",
                    },
                ],
            }
        },
    )
    assert r.status_code == 200
    titles = {i["product"]["title"] for i in r.json()["items"]}
    assert titles == {"Cheap InStock", "Pandemic Legacy"}


def test_post_query_pagination_and_total(client: TestClient, session: Session):
    _store(session)
    for i in range(10):
        _product(session, f"Game {i}", float(i * 5))
    r = client.post("/api/browse/query", json={"page": 1, "limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 3
    assert data["total"] == 10

    r2 = client.post("/api/browse/query", json={"page": 4, "limit": 3})
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["items"]) == 1  # 10 items, page 4 of limit 3 = last 1


def test_post_query_include_hidden(client: TestClient, session: Session):
    _store(session)
    _product(session, "Visible", 20.0, hidden=False)
    _product(session, "Hidden", 20.0, hidden=True)
    # by default hidden excluded
    r = client.post("/api/browse/query", json={})
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "Hidden" not in titles

    r2 = client.post("/api/browse/query", json={"include_hidden": True})
    assert r2.status_code == 200
    titles2 = [i["product"]["title"] for i in r2.json()["items"]]
    assert "Hidden" in titles2


def test_post_query_unknown_field_returns_422(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "nonexistent",
                "op": "eq",
                "value": "x",
            }
        },
    )
    assert r.status_code == 422


def test_post_query_bad_op_returns_422(client: TestClient, session: Session):
    _store(session)
    _product(session, "Catan", 30.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "price",
                "op": "contains",
                "value": "foo",
            }
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Integration: GET /api/browse/fields
# ---------------------------------------------------------------------------


def test_get_fields_returns_list(client: TestClient):
    r = client.get("/api/browse/fields")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    names = {f["name"] for f in data}
    assert "price" in names
    assert "title" in names
    assert "available" in names
    assert "bgg_rating" in names
    assert "discount_pct" in names


def test_get_fields_price_ops(client: TestClient):
    r = client.get("/api/browse/fields")
    price = next(f for f in r.json() if f["name"] == "price")
    ops = set(price["ops"])
    assert {"gte", "lte", "gt", "lt", "eq", "ne", "in", "not_in"}.issubset(ops)
    assert "contains" not in ops


def test_get_fields_title_ops(client: TestClient):
    r = client.get("/api/browse/fields")
    title = next(f for f in r.json() if f["name"] == "title")
    ops = set(title["ops"])
    assert {"contains", "starts_with", "ends_with", "eq", "ne"}.issubset(ops)


def test_get_fields_available_ops(client: TestClient):
    r = client.get("/api/browse/fields")
    avail = next(f for f in r.json() if f["name"] == "available")
    ops = set(avail["ops"])
    assert "eq" in ops
    assert "gt" not in ops
    assert "contains" not in ops


# ---------------------------------------------------------------------------
# Hidden products visibility
# ---------------------------------------------------------------------------


def test_hidden_excluded_by_default(client: TestClient, session: Session):
    """Hidden products must not appear in default browse results."""
    _store(session)
    _product(session, "Visible", 30.0)
    _product(session, "HiddenGame", 30.0, hidden=True)
    r = client.post(
        "/api/browse/query", json={"filters": None, "sorts": [], "page": 1, "limit": 50}
    )
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "Visible" in titles
    assert "HiddenGame" not in titles


def test_hidden_filter_eq_true_shows_only_hidden(client: TestClient, session: Session):
    """Filtering hidden=true must return hidden products and skip visible ones."""
    _store(session)
    _product(session, "Visible", 30.0)
    _product(session, "HiddenGame", 30.0, hidden=True)
    body = {
        "filters": {"type": "condition", "field": "hidden", "op": "eq", "value": True},
        "sorts": [],
        "page": 1,
        "limit": 50,
    }
    r = client.post("/api/browse/query", json=body)
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "HiddenGame" in titles
    assert "Visible" not in titles


def test_hidden_filter_eq_false_excludes_hidden(client: TestClient, session: Session):
    """Filtering hidden=false must behave same as default (no hidden products)."""
    _store(session)
    _product(session, "Visible", 30.0)
    _product(session, "HiddenGame", 30.0, hidden=True)
    body = {
        "filters": {"type": "condition", "field": "hidden", "op": "eq", "value": False},
        "sorts": [],
        "page": 1,
        "limit": 50,
    }
    r = client.post("/api/browse/query", json=body)
    assert r.status_code == 200
    titles = [i["product"]["title"] for i in r.json()["items"]]
    assert "Visible" in titles
    assert "HiddenGame" not in titles


# ---------------------------------------------------------------------------
# is_watched field
# ---------------------------------------------------------------------------


def _watch(session: Session, product: Product) -> None:
    session.add(WatchlistItem(game_id=product.game_id))
    session.commit()


def test_is_watched_false_by_default(session: Session):
    """Products not in watchlist have is_watched=false."""
    _store(session)
    p = _product(session, "Catan", 30.0)
    rows = query_products(
        session,
        filter_node=Condition(field="is_watched", op="eq", value=False),
    )
    ids = [r[0].id for r in rows]
    assert p.id in ids


def test_is_watched_true_after_watch(session: Session):
    """Watched product appears in is_watched=true filter."""
    _store(session)
    p = _product(session, "Wingspan", 60.0)
    _watch(session, p)
    rows = query_products(
        session,
        filter_node=Condition(field="is_watched", op="eq", value=True),
    )
    ids = [r[0].id for r in rows]
    assert p.id in ids


def test_is_watched_separates_watched_from_unwatched(session: Session):
    """is_watched=true only returns watched; unwatched excluded."""
    _store(session)
    watched = _product(session, "Watched", 30.0)
    _product(session, "Unwatched", 30.0)
    _watch(session, watched)
    rows = query_products(
        session,
        filter_node=Condition(field="is_watched", op="eq", value=True),
    )
    titles = [r[2].title for r in rows]
    assert "Watched" in titles
    assert "Unwatched" not in titles


def test_is_watched_false_after_unwatch(session: Session):
    """Removing from the watchlist is a soft delete (active=False) — the
    product must stop matching is_watched=true."""
    _store(session)
    p = _product(session, "Unwatched Again", 40.0)
    item = WatchlistItem(game_id=p.game_id)
    session.add(item)
    session.commit()

    item.active = False
    session.add(item)
    session.commit()

    watched = query_products(
        session,
        filter_node=Condition(field="is_watched", op="eq", value=True),
    )
    assert p.id not in [r[0].id for r in watched]

    unwatched = query_products(
        session,
        filter_node=Condition(field="is_watched", op="eq", value=False),
    )
    assert p.id in [r[0].id for r in unwatched]


def test_is_watched_count_excludes_inactive(session: Session):
    """count_products must agree with query_products after a soft delete."""
    _store(session)
    active = _product(session, "Still Watched", 30.0)
    removed = _product(session, "Removed", 30.0)
    session.add(WatchlistItem(game_id=active.game_id))
    session.add(WatchlistItem(game_id=removed.game_id, active=False))
    session.commit()

    node = Condition(field="is_watched", op="eq", value=True)
    assert count_products(session, filter_node=node) == 1
    assert [r[0].id for r in query_products(session, filter_node=node)] == [active.id]


def test_is_watched_in_fields_endpoint(client: TestClient):
    """is_watched field appears in /api/browse/fields with bool ops."""
    r = client.get("/api/browse/fields")
    field = next((f for f in r.json() if f["name"] == "is_watched"), None)
    assert field is not None
    assert field["type"] == "bool"
    assert "eq" in field["ops"]


# ---------------------------------------------------------------------------
# random sort
# ---------------------------------------------------------------------------


def test_random_sort_returns_all_results(session: Session):
    """random sort returns same count as unsorted query."""
    _store(session)
    for i in range(5):
        _product(session, f"Game{i}", float(10 + i))
    rows_sorted = query_products(session, sorts=[SortSpec(field="random", dir="asc")])
    rows_default = query_products(session)
    assert len(rows_sorted) == len(rows_default)


def test_random_sort_in_fields_endpoint(client: TestClient):
    """random sort appears in /api/browse/fields as sortable, not filterable."""
    r = client.get("/api/browse/fields")
    field = next((f for f in r.json() if f["name"] == "random"), None)
    assert field is not None
    assert field["sortable"] is True
    assert field["filterable"] is False


def test_random_sort_via_api(client: TestClient, session: Session):
    """POST /browse/query with random sort returns 200 with results."""
    _store(session)
    _product(session, "Alpha", 10.0)
    _product(session, "Beta", 20.0)
    r = client.post(
        "/api/browse/query",
        json={
            "filters": None,
            "sorts": [{"field": "random", "dir": "asc"}],
            "page": 1,
            "limit": 10,
        },
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# back_in_stock field
# ---------------------------------------------------------------------------


def _add_snapshot(
    session: Session, product: Product, price: float, available: bool
) -> None:
    """Add a second snapshot to simulate stock/price change."""
    session.add(
        PriceSnapshot(
            product_id=product.id,
            price=price,
            available=available,
            recorded_at=datetime.now(UTC),
        )
    )
    session.commit()


def test_back_in_stock_true_when_was_out(session: Session):
    """back_in_stock=true: product was unavailable, now available."""
    _store(session)
    p = _product(session, "Restock", 30.0, available=False)
    _add_snapshot(session, p, 30.0, available=True)
    rows = query_products(
        session,
        filter_node=Condition(field="back_in_stock", op="eq", value=True),
    )
    ids = [r[0].id for r in rows]
    assert p.id in ids


def test_back_in_stock_false_when_always_in_stock(session: Session):
    """back_in_stock=true excludes products that were already in stock."""
    _store(session)
    p = _product(session, "AlwaysInStock", 30.0, available=True)
    _add_snapshot(session, p, 30.0, available=True)
    rows = query_products(
        session,
        filter_node=Condition(field="back_in_stock", op="eq", value=True),
    )
    ids = [r[0].id for r in rows]
    assert p.id not in ids


def test_back_in_stock_in_fields_endpoint(client: TestClient):
    r = client.get("/api/browse/fields")
    field = next((f for f in r.json() if f["name"] == "back_in_stock"), None)
    assert field is not None
    assert field["type"] == "bool"


# ---------------------------------------------------------------------------
# price_pct_change field
# ---------------------------------------------------------------------------


def test_price_pct_change_positive_on_increase(session: Session):
    """price_pct_change > 0 when price rose."""
    _store(session)
    p = _product(session, "RisingGame", 100.0)
    _add_snapshot(session, p, 120.0, available=True)
    rows = query_products(
        session,
        filter_node=Condition(field="price_pct_change", op="gt", value=0),
    )
    ids = [r[0].id for r in rows]
    assert p.id in ids


def test_price_pct_change_negative_on_drop(session: Session):
    """price_pct_change < 0 when price dropped."""
    _store(session)
    p = _product(session, "DroppingGame", 100.0)
    _add_snapshot(session, p, 80.0, available=True)
    rows = query_products(
        session,
        filter_node=Condition(field="price_pct_change", op="lt", value=0),
    )
    ids = [r[0].id for r in rows]
    assert p.id in ids


def test_price_pct_change_in_fields_endpoint(client: TestClient):
    r = client.get("/api/browse/fields")
    field = next((f for f in r.json() if f["name"] == "price_pct_change"), None)
    assert field is not None
    assert field["type"] == "float"
