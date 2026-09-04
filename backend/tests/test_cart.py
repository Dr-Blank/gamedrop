from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import CartItem, Game, PriceSnapshot, Product

from .factories import make_product, make_store


def _priced(session: Session, product: Product, price: float, available: bool = True):
    session.add(PriceSnapshot(product_id=product.id, price=price, available=available))
    session.commit()
    return product


def _seed_one(session: Session, price: float = 1200.0) -> Product:
    make_store(session, "s1")
    return _priced(session, make_product(session, title="Catan"), price)


def _seed_two_shops(
    session: Session, cheap: float = 900.0, dear: float = 1200.0, cheap_stock=True
):
    """One game sold by two shops, so the row has a choice to make."""
    make_store(session, "s1")
    make_store(session, "s2")
    dear_listing = _priced(session, make_product(session, title="Azul"), dear)
    game = session.get(Game, dear_listing.game_id)
    cheap_listing = _priced(
        session,
        make_product(session, store_id="s2", title="Azul", external_id="e2", game=game),
        cheap,
        available=cheap_stock,
    )
    return dear_listing, cheap_listing


def test_empty_cart(client: TestClient):
    body = client.get("/api/cart/").json()
    assert body["items"] == []
    assert body["summary"]["total"] == 0
    assert body["summary"]["count"] == 0


def test_add_by_listing_queues_the_game(client: TestClient, session: Session):
    product = _seed_one(session)
    r = client.post("/api/cart/", json={"product_id": product.id})
    assert r.status_code == 200
    assert r.json()["game_id"] == product.game_id
    # Unpinned by default: the row follows the cheapest buyable offer.
    assert r.json()["product_id"] is None


def test_add_can_pin_the_shop_it_came_from(client: TestClient, session: Session):
    dear, cheap = _seed_two_shops(session)
    r = client.post("/api/cart/", json={"product_id": dear.id, "pin_store": True})
    assert r.json()["product_id"] == dear.id

    row = client.get("/api/cart/").json()["items"][0]
    assert row["offer"]["store_id"] == "s1"
    assert row["pinned"] is True


def test_unpinned_row_quotes_the_cheapest_in_stock_offer(
    client: TestClient, session: Session
):
    dear, cheap = _seed_two_shops(session)
    client.post("/api/cart/", json={"product_id": dear.id})

    row = client.get("/api/cart/").json()["items"][0]
    assert row["offer"]["product_id"] == cheap.id
    assert row["offer"]["price"] == 900.0


def test_out_of_stock_cheapest_does_not_win_the_quote(
    client: TestClient, session: Session
):
    """A price you cannot pay is not the price to budget against."""
    dear, cheap = _seed_two_shops(session, cheap_stock=False)
    client.post("/api/cart/", json={"product_id": dear.id})

    row = client.get("/api/cart/").json()["items"][0]
    assert row["offer"]["product_id"] == dear.id


def test_add_is_idempotent_per_game(client: TestClient, session: Session):
    product = _seed_one(session)
    first = client.post("/api/cart/", json={"product_id": product.id}).json()
    again = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert first["id"] == again["id"]
    assert len(client.get("/api/cart/").json()["items"]) == 1


def test_add_records_the_price_it_was_queued_at(client: TestClient, session: Session):
    product = _seed_one(session, price=1200.0)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert item["added_price"] == 1200.0

    session.add(PriceSnapshot(product_id=product.id, price=1000.0))
    session.commit()
    row = client.get("/api/cart/").json()["items"][0]
    assert row["price_move"] == -200.0


def test_add_rejects_unknown_listing(client: TestClient):
    assert client.post("/api/cart/", json={"product_id": 999}).status_code == 404


def test_add_rejects_an_unknown_priority(client: TestClient, session: Session):
    product = _seed_one(session)
    r = client.post("/api/cart/", json={"product_id": product.id, "priority": "urgent"})
    assert r.status_code == 422


def test_reorder_sets_buy_order(client: TestClient, session: Session):
    make_store(session, "s1")
    a = _priced(session, make_product(session, title="A", external_id="a"), 100.0)
    b = _priced(session, make_product(session, title="B", external_id="b"), 200.0)
    first = client.post("/api/cart/", json={"product_id": a.id}).json()
    second = client.post("/api/cart/", json={"product_id": b.id}).json()

    body = client.post(
        "/api/cart/reorder", json={"ids": [second["id"], first["id"]]}
    ).json()
    assert [i["cart"]["id"] for i in body["items"]] == [second["id"], first["id"]]


def test_reorder_rejects_unknown_ids(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert (
        client.post("/api/cart/reorder", json={"ids": [item["id"], 999]}).status_code
        == 404
    )


def test_patch_switches_the_shop(client: TestClient, session: Session):
    dear, cheap = _seed_two_shops(session)
    item = client.post(
        "/api/cart/", json={"product_id": cheap.id, "pin_store": True}
    ).json()

    r = client.patch(f"/api/cart/{item['id']}", json={"product_id": dear.id})
    assert r.status_code == 200
    assert client.get("/api/cart/").json()["items"][0]["offer"]["store_id"] == "s1"


def test_patch_rejects_a_listing_of_another_game(client: TestClient, session: Session):
    make_store(session, "s1")
    mine = _priced(session, make_product(session, title="A", external_id="a"), 100.0)
    other = _priced(session, make_product(session, title="B", external_id="b"), 200.0)
    item = client.post("/api/cart/", json={"product_id": mine.id}).json()

    r = client.patch(f"/api/cart/{item['id']}", json={"product_id": other.id})
    assert r.status_code == 404


def test_unpin_returns_the_row_to_the_cheapest_offer(
    client: TestClient, session: Session
):
    dear, cheap = _seed_two_shops(session)
    item = client.post(
        "/api/cart/", json={"product_id": dear.id, "pin_store": True}
    ).json()

    client.patch(f"/api/cart/{item['id']}", json={"unpin": True})
    row = client.get("/api/cart/").json()["items"][0]
    assert row["pinned"] is False
    assert row["offer"]["product_id"] == cheap.id


def test_patch_stores_a_markdown_note(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    note = "## why\n- fills the **gateway** gap"

    r = client.patch(f"/api/cart/{item['id']}", json={"note": note})
    assert r.json()["note"] == note
    assert client.get("/api/cart/").json()["items"][0]["cart"]["note"] == note


def test_blank_note_clears_it(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post(
        "/api/cart/", json={"product_id": product.id, "note": "temp"}
    ).json()
    assert (
        client.patch(f"/api/cart/{item['id']}", json={"note": "  "}).json()["note"]
        is None
    )


def test_max_price_flags_a_row_that_is_too_dear(client: TestClient, session: Session):
    product = _seed_one(session, price=1200.0)
    item = client.post(
        "/api/cart/", json={"product_id": product.id, "max_price": 1000.0}
    ).json()

    body = client.get("/api/cart/").json()
    assert body["items"][0]["over_max"] is True
    assert body["summary"]["over_max"] == 1

    client.patch(f"/api/cart/{item['id']}", json={"clear_max_price": True})
    assert client.get("/api/cart/").json()["summary"]["over_max"] == 0


def test_quantity_multiplies_the_line(client: TestClient, session: Session):
    product = _seed_one(session, price=500.0)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.patch(f"/api/cart/{item['id']}", json={"quantity": 3})
    assert client.get("/api/cart/").json()["summary"]["total"] == 1500.0


def test_summary_totals_and_per_store_baskets(client: TestClient, session: Session):
    """One order per shop is what actually gets placed, so the split is reported."""
    make_store(session, "s1")
    make_store(session, "s2")
    a = _priced(session, make_product(session, title="A", external_id="a"), 100.0)
    b = _priced(
        session,
        make_product(session, store_id="s2", title="B", external_id="b"),
        250.0,
    )
    client.post("/api/cart/", json={"product_id": a.id})
    client.post("/api/cart/", json={"product_id": b.id})

    summary = client.get("/api/cart/").json()["summary"]
    assert summary["total"] == 350.0
    assert summary["count"] == 2
    baskets = {s["store_id"]: s for s in summary["by_store"]}
    assert baskets["s2"]["total"] == 250.0
    assert baskets["s1"]["count"] == 1


def test_summary_counts_what_cannot_be_bought(client: TestClient, session: Session):
    make_store(session, "s1")
    out = _priced(
        session,
        make_product(session, title="A", external_id="a"),
        300.0,
        available=False,
    )
    client.post("/api/cart/", json={"product_id": out.id})

    summary = client.get("/api/cart/").json()["summary"]
    assert summary["total"] == 300.0
    assert summary["in_stock_total"] == 0
    assert summary["unavailable"] == 1


def test_budget_cutline_marks_the_first_unaffordable_row(
    client: TestClient, session: Session
):
    make_store(session, "s1")
    a = _priced(session, make_product(session, title="A", external_id="a"), 600.0)
    b = _priced(session, make_product(session, title="B", external_id="b"), 600.0)
    client.post("/api/cart/", json={"product_id": a.id})
    client.post("/api/cart/", json={"product_id": b.id})
    client.put("/api/cart/budget", json={"amount": 1000.0})

    summary = client.get("/api/cart/").json()["summary"]
    assert summary["budget"] == 1000.0
    assert summary["cut_index"] == 1
    assert summary["budget_remaining"] == -200.0


def test_budget_clears(client: TestClient):
    client.put("/api/cart/budget", json={"amount": 500.0})
    assert (
        client.put("/api/cart/budget", json={"amount": None}).json()["budget"] is None
    )
    assert client.get("/api/cart/").json()["summary"]["cut_index"] is None


def test_switch_suggestion_names_the_cheaper_shop(client: TestClient, session: Session):
    dear, cheap = _seed_two_shops(session)
    client.post("/api/cart/", json={"product_id": dear.id, "pin_store": True})

    body = client.get("/api/cart/").json()
    assert body["summary"]["switch_savings"] == 300.0
    switch = body["switches"][0]
    assert switch["to_store"] == "s2"
    assert switch["to_product_id"] == cheap.id
    assert switch["saves"] == 300.0


def test_unpinned_rows_suggest_nothing_to_switch(client: TestClient, session: Session):
    dear, cheap = _seed_two_shops(session)
    client.post("/api/cart/", json={"product_id": dear.id})
    assert client.get("/api/cart/").json()["switches"] == []


def test_purchase_moves_the_row_onto_the_record(client: TestClient, session: Session):
    product = _seed_one(session, price=1200.0)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()

    bought = client.post(f"/api/cart/{item['id']}/purchase").json()
    assert bought["purchased_price"] == 1200.0
    assert client.get("/api/cart/").json()["items"] == []
    assert len(client.get("/api/cart/purchased").json()["items"]) == 1


def test_purchase_can_be_undone(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.post(f"/api/cart/{item['id']}/purchase")

    client.delete(f"/api/cart/{item['id']}/purchase")
    assert len(client.get("/api/cart/").json()["items"]) == 1
    assert client.get("/api/cart/purchased").json()["items"] == []


def test_remove_from_cart(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert client.delete(f"/api/cart/{item['id']}").json() == {"ok": True}
    assert client.get("/api/cart/").json()["items"] == []

    archived = session.get(CartItem, item["id"])
    session.refresh(archived)
    assert archived.removed_at is not None


def test_re_adding_restores_the_removed_row(client: TestClient, session: Session):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.patch(
        f"/api/cart/{item['id']}",
        json={
            "note": "second edition",
            "priority": "must",
            "max_price": 999,
            "quantity": 3,
        },
    )
    client.delete(f"/api/cart/{item['id']}")

    back = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert back["id"] == item["id"]
    assert back["note"] == "second edition"
    assert back["priority"] == "must"
    assert back["max_price"] == 999
    assert back["quantity"] == 3
    assert len(client.get("/api/cart/").json()["items"]) == 1


def test_re_adding_prefers_what_the_request_asks_for(
    client: TestClient, session: Session
):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.patch(f"/api/cart/{item['id']}", json={"note": "old", "priority": "must"})
    client.delete(f"/api/cart/{item['id']}")

    back = client.post(
        "/api/cart/", json={"product_id": product.id, "note": "new"}
    ).json()
    assert back["note"] == "new"
    assert back["priority"] == "must"


def test_re_adding_after_a_purchase_keeps_the_note(
    client: TestClient, session: Session
):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.patch(f"/api/cart/{item['id']}", json={"note": "for the shelf"})
    client.post(f"/api/cart/{item['id']}/purchase")

    back = client.post("/api/cart/", json={"product_id": product.id}).json()
    assert back["id"] != item["id"]
    assert back["note"] == "for the shelf"
    assert len(client.get("/api/cart/purchased").json()["items"]) == 1


def test_removed_rows_stay_out_of_the_purchased_list(
    client: TestClient, session: Session
):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.post(f"/api/cart/{item['id']}/purchase")
    client.delete(f"/api/cart/{item['id']}")
    assert client.get("/api/cart/purchased").json()["items"] == []


def test_remove_not_found(client: TestClient):
    assert client.delete("/api/cart/999").status_code == 404


def test_browse_can_filter_on_the_queue(client: TestClient, session: Session):
    make_store(session, "s1")
    queued = _priced(session, make_product(session, title="A", external_id="a"), 100.0)
    _priced(session, make_product(session, title="B", external_id="b"), 200.0)
    client.post("/api/cart/", json={"product_id": queued.id})

    items = client.post(
        "/api/browse/query",
        json={
            "filters": {
                "type": "condition",
                "field": "is_in_cart",
                "op": "eq",
                "value": True,
            }
        },
    ).json()["items"]
    assert [i["game"]["id"] for i in items] == [queued.game_id]


def test_a_bought_game_leaves_the_queue_and_reads_as_owned(
    client: TestClient, session: Session
):
    product = _seed_one(session)
    item = client.post("/api/cart/", json={"product_id": product.id}).json()
    client.post(f"/api/cart/{item['id']}/purchase")

    def matching(field):
        return client.post(
            "/api/browse/query",
            json={
                "filters": {
                    "type": "condition",
                    "field": field,
                    "op": "eq",
                    "value": True,
                }
            },
        ).json()["items"]

    assert matching("is_in_cart") == []
    assert [i["game"]["id"] for i in matching("is_owned")] == [product.game_id]


def test_queue_fields_are_introspectable(client: TestClient):
    names = {f["name"] for f in client.get("/api/browse/fields").json()}
    assert {"is_in_cart", "is_owned"} <= names
