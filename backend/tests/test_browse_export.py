from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import CartItem, Game, PriceSnapshot

from .factories import make_product, make_store, watch

COLUMNS = {
    "game",
    "store",
    "price",
    "in_stock",
    "cheapest_in_stock_price",
    "cheapest_in_stock_store",
    "store_count",
    "watched",
    "in_cart",
    "owned",
}


def _price(session: Session, product, price: float, available: bool = True):
    session.add(PriceSnapshot(product_id=product.id, price=price, available=available))
    session.commit()


def _seed(session: Session):
    make_store(session, "s1", name="Store One")
    make_store(session, "s2", name="Store Two")

    catan = make_product(session, store_id="s1", title="Catan")
    catan_two = make_product(
        session, store_id="s2", title="Catan", game=session.get(Game, catan.game_id)
    )
    azul = make_product(session, store_id="s1", title="Azul")

    _price(session, catan, 300.0, True)
    _price(session, catan_two, 250.0, False)
    _price(session, azul, 100.0, True)
    return catan, catan_two, azul


def _export(client: TestClient, **body):
    r = client.post("/api/browse/export", json=body)
    assert r.status_code == 200
    return r.json()


def test_export_has_a_row_per_shop_offer(client: TestClient, session: Session):
    _seed(session)
    data = _export(client)
    assert data["count"] == 3
    pairs = {(row["game"], row["store"]) for row in data["rows"]}
    assert pairs == {
        ("Catan", "Store One"),
        ("Catan", "Store Two"),
        ("Azul", "Store One"),
    }


def test_export_columns_are_the_watered_down_set(client: TestClient, session: Session):
    _seed(session)
    rows = _export(client)["rows"]
    assert all(set(row) == COLUMNS for row in rows)


def test_export_cheapest_skips_out_of_stock(client: TestClient, session: Session):
    _seed(session)
    rows = [r for r in _export(client)["rows"] if r["game"] == "Catan"]
    assert {r["cheapest_in_stock_price"] for r in rows} == {300.0}
    assert {r["cheapest_in_stock_store"] for r in rows} == {"Store One"}
    assert {r["store_count"] for r in rows} == {2}


def test_export_cheapest_is_none_when_nothing_in_stock(
    client: TestClient, session: Session
):
    make_store(session, "s1", name="Store One")
    product = make_product(session, store_id="s1", title="Azul")
    _price(session, product, 100.0, available=False)

    row = _export(client)["rows"][0]
    assert row["cheapest_in_stock_price"] is None
    assert row["cheapest_in_stock_store"] is None


def test_export_respects_filters(client: TestClient, session: Session):
    _seed(session)
    data = _export(
        client,
        filters={"type": "condition", "field": "store_id", "op": "eq", "value": "s2"},
    )
    # The filter picks the game, but the export still carries every shop selling it.
    assert {(r["game"], r["store"]) for r in data["rows"]} == {
        ("Catan", "Store One"),
        ("Catan", "Store Two"),
    }


def test_export_skips_hidden_games(client: TestClient, session: Session):
    _, _, azul = _seed(session)
    game = session.get(Game, azul.game_id)
    game.hidden = True
    session.add(game)
    session.commit()

    assert {r["game"] for r in _export(client)["rows"]} == {"Catan"}


def test_export_carries_intent_flags(client: TestClient, session: Session):
    catan, _, azul = _seed(session)
    watch(session, catan)
    session.add(CartItem(game_id=azul.game_id))
    session.commit()

    by_game = {r["game"]: r for r in _export(client)["rows"]}
    assert by_game["Catan"]["watched"] is True
    assert by_game["Catan"]["in_cart"] is False
    assert by_game["Azul"]["in_cart"] is True
    assert by_game["Azul"]["watched"] is False
