"""Games: merging listings, suggestions, comparison payload, BGG identity."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import (
    Game,
    GameAlias,
    MergeRejection,
    PriceSnapshot,
    Product,
    ProductOverride,
    WatchListingState,
    WatchlistItem,
)
from app.repositories import catalog as repo
from app.services import games as service
from app.text_search import match_key, similarity

from .factories import make_product, make_store


def _stores(session: Session):
    make_store(session, "shopify-a", name="A")
    make_store(session, "woo-b", name="B", type="woocommerce")


def _listing(
    session: Session,
    store_id: str,
    title: str,
    *,
    price: float | None = None,
    available: bool = True,
    bgg_id: int | None = None,
    recorded_at: datetime | None = None,
    image_url: str | None = None,
) -> Product:
    product = make_product(
        session,
        store_id=store_id,
        title=title,
        external_id=f"{store_id}:{title}",
        bgg_id=bgg_id,
        image_url=image_url,
        url=f"https://{store_id}.test/{title}",
    )
    if price is not None:
        session.add(
            PriceSnapshot(
                product_id=product.id,
                price=price,
                available=available,
                recorded_at=recorded_at or datetime.utcnow(),
            )
        )
        session.commit()
    return product


def _game(session: Session, product: Product) -> Game:
    session.expire_all()
    return session.get(Game, session.get(Product, product.id).game_id)


# --- title matching --------------------------------------------------------


def test_match_key_strips_marketing_tail():
    assert match_key("Catan | Strategy Board Game for 3-4 Players, Ages 10+") == "catan"


def test_match_key_keeps_expansion_names():
    assert "seafarers" in match_key("Catan: Seafarers Expansion")


def test_match_key_falls_back_when_all_words_are_noise():
    assert match_key("Board Game Set") != ""


def test_similarity_matches_noisy_against_clean_title():
    assert (
        similarity("Catan", "Catan &ndash; Strategy Board Game | 3-4 Players, Ages 10+")
        >= 100
    )


def test_similarity_separates_different_games():
    assert similarity("Catan Board Game", "Carcassonne Board Game") < 78


# --- suggestions -----------------------------------------------------------


def test_suggestions_find_the_same_game_at_another_store(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(
        session, "woo-b", "Catan | Strategy Board Game for Family, Ages 10+", price=2500
    )
    _listing(session, "woo-b", "Carcassonne Board Game", price=1800)

    r = client.get(f"/api/products/{a.id}/merge-suggestions")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["item"]["product"]["id"] for i in items] == [b.id]
    assert items[0]["score"] >= 78


def test_suggestions_skip_same_store(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    _listing(session, "shopify-a", "Catan Board Game", price=3100)

    assert client.get(f"/api/products/{a.id}/merge-suggestions").json()["items"] == []


def test_suggestions_skip_hidden(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    _game(session, b).hidden = True
    session.commit()

    items = client.get(f"/api/products/{a.id}/merge-suggestions").json()["items"]
    assert [i["item"]["product"]["id"] for i in items] == [b.id] or items == []


def test_suggestions_skip_rejected_pair(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)

    assert (
        client.post(
            f"/api/products/{a.id}/reject-merge", json={"other_product_id": b.id}
        ).status_code
        == 200
    )
    assert client.get(f"/api/products/{a.id}/merge-suggestions").json()["items"] == []
    # Rejection is symmetric — the pair stays gone from the other page too.
    assert client.get(f"/api/products/{b.id}/merge-suggestions").json()["items"] == []


def test_suggestions_skip_listings_of_the_same_game(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    service.merge(session, a.id, b.id)

    assert client.get(f"/api/products/{a.id}/merge-suggestions").json()["items"] == []


def test_suggestions_404_for_missing_listing(client: TestClient):
    assert client.get("/api/products/9999/merge-suggestions").status_code == 404


def test_suggestion_queue_pairs_cross_store_matches(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul | Award Winning Tile Game", price=1900)

    items = client.get("/api/games/suggestions").json()["items"]
    assert len(items) == 1
    pair = {items[0]["left"]["product"]["id"], items[0]["right"]["product"]["id"]}
    assert pair == {a.id, b.id}


def test_suggestion_queue_reports_total_beyond_the_page(
    client: TestClient, session: Session
):
    _stores(session)
    for title in ("Azul", "Catan", "Pandemic"):
        _listing(session, "shopify-a", title, price=2000)
        _listing(session, "woo-b", f"{title} | Board Game", price=1900)

    body = client.get("/api/games/suggestions?limit=2").json()
    assert len(body["items"]) == 2
    assert body["total"] == 3


def test_suggestion_queue_shows_each_listing_once(client: TestClient, session: Session):
    """Three shops on one game yield one pair, not every combination."""
    _stores(session)
    make_store(session, "shopify-c", name="C")
    _listing(session, "shopify-a", "Azul", price=2000)
    _listing(session, "woo-b", "Azul", price=1900)
    _listing(session, "shopify-c", "Azul", price=1800)

    body = client.get("/api/games/suggestions").json()
    assert len(body["items"]) == 1
    seen = [
        body["items"][0]["left"]["product"]["id"],
        body["items"][0]["right"]["product"]["id"],
    ]
    assert len(set(seen)) == 2


def test_suggestion_queue_honours_a_score_floor(client: TestClient, session: Session):
    """A floor drops the loose matches and keeps the certain ones."""
    _stores(session)
    _listing(session, "shopify-a", "Catan", price=2000)
    _listing(session, "woo-b", "Catan Board Game", price=1900)
    _listing(session, "shopify-a", "Azul", price=2000)
    _listing(session, "woo-b", "Azul Summer Pavilion", price=1900)

    assert client.get("/api/games/suggestions").json()["total"] == 2
    body = client.get("/api/games/suggestions?min_score=180").json()
    assert body["total"] == 1
    titles = {body["items"][0]["left"]["game"]["title"]}
    assert titles == {"Catan"}


def test_decide_applies_merges_and_rejections_in_one_call(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul Board Game", price=1900)
    c = _listing(session, "shopify-a", "Catan", price=3000)
    d = _listing(session, "woo-b", "Catan Board Game", price=2900)

    r = client.post(
        "/api/games/suggestions/decide",
        json={"merges": [[a.id, b.id]], "rejects": [[c.id, d.id]]},
    )
    assert r.json() == {"merged": 1, "rejected": 1, "unrejected": 0, "skipped": 0}
    assert _game(session, a).id == _game(session, b).id
    assert session.get(MergeRejection, (min(c.id, d.id), max(c.id, d.id))) is not None


def test_rejected_queue_lists_turned_down_pairs(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul Board Game", price=1900)
    client.post(f"/api/products/{a.id}/reject-merge", json={"other_product_id": b.id})

    body = client.get("/api/games/suggestions/rejected").json()
    assert body["total"] == 1
    pair = {
        body["items"][0]["left"]["product"]["id"],
        body["items"][0]["right"]["product"]["id"],
    }
    assert pair == {a.id, b.id}


def test_rejected_queue_honours_a_score_floor(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul Summer Pavilion", price=1900)
    client.post(f"/api/products/{a.id}/reject-merge", json={"other_product_id": b.id})

    assert client.get("/api/games/suggestions/rejected").json()["total"] == 1
    assert (
        client.get("/api/games/suggestions/rejected?min_score=180").json()["total"] == 0
    )


def test_rejected_queue_drops_pairs_already_on_one_game(
    client: TestClient, session: Session
):
    """Merging overrules the rejection, so there is nothing to reconsider."""
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul Board Game", price=1900)
    session.add(
        MergeRejection(product_a_id=min(a.id, b.id), product_b_id=max(a.id, b.id))
    )
    session.commit()
    service.merge(session, a.id, b.id)

    assert client.get("/api/games/suggestions/rejected").json()["items"] == []


def test_unrejecting_puts_the_pair_back_in_the_queue(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)
    b = _listing(session, "woo-b", "Azul Board Game", price=1900)
    client.post(f"/api/products/{a.id}/reject-merge", json={"other_product_id": b.id})
    assert client.get("/api/games/suggestions").json()["total"] == 0

    r = client.post("/api/games/suggestions/decide", json={"unrejects": [[a.id, b.id]]})
    assert r.json()["unrejected"] == 1
    assert client.get("/api/games/suggestions/rejected").json()["total"] == 0
    assert client.get("/api/games/suggestions").json()["total"] == 1


def test_decide_skips_a_pair_that_no_longer_applies(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Azul", price=2000)

    r = client.post("/api/games/suggestions/decide", json={"merges": [[a.id, 9999]]})
    assert r.json()["skipped"] == 1
    assert r.json()["merged"] == 0


# --- manual candidate search ----------------------------------------------


def test_manual_search_finds_a_candidate_the_ranking_missed(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Cat in the Box", price=1500)
    b = _listing(session, "woo-b", "Nekobako Deluxe Edition", price=1400)
    assert client.get(f"/api/products/{a.id}/merge-suggestions").json()["items"] == []

    r = client.get(f"/api/products/{a.id}/merge-candidates?q=nekobako")
    assert r.status_code == 200
    assert [i["item"]["product"]["id"] for i in r.json()["items"]] == [b.id]


def test_manual_search_flags_a_rejected_candidate(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    service.reject(session, a.id, b.id)

    items = client.get(f"/api/products/{a.id}/merge-candidates?q=catan").json()["items"]
    assert [i["rejected"] for i in items] == [True]


def test_manual_search_excludes_the_same_game(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    service.merge(session, a.id, b.id)

    items = client.get(f"/api/products/{a.id}/merge-candidates?q=catan").json()["items"]
    assert items == []


def test_manual_search_needs_a_query(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    assert (
        client.get(f"/api/products/{a.id}/merge-candidates?q=  ").json()["items"] == []
    )


# --- merge / unmerge -------------------------------------------------------


def test_merge_puts_both_listings_on_one_game(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan | Board Game for Family", price=2500)

    r = client.post(f"/api/products/{a.id}/merge", json={"other_product_id": b.id})
    assert r.status_code == 200
    payload = r.json()
    assert payload["listing_count"] == 2
    assert sorted(payload["store_ids"]) == ["shopify-a", "woo-b"]
    # The shorter of the two names is the cleaner one.
    assert payload["game"]["title"] == "Catan"
    assert _game(session, a).id == _game(session, b).id


def test_merge_keeps_the_older_game_and_deletes_the_other(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    older = min(a.game_id, b.game_id)

    payload = service.merge(session, a.id, b.id)
    assert payload["game"].id == older
    assert len(session.exec(select(Game)).all()) == 1


def test_merge_is_idempotent(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)

    client.post(f"/api/products/{a.id}/merge", json={"other_product_id": b.id})
    r = client.post(f"/api/products/{a.id}/merge", json={"other_product_id": b.id})
    assert r.json()["listing_count"] == 2
    assert len(session.exec(select(Game)).all()) == 1


def test_merge_fuses_games_with_several_listings(client: TestClient, session: Session):
    _stores(session)
    make_store(session, "woo-c", name="C", type="woocommerce")
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    c = _listing(session, "woo-c", "Catan Strategy Game", price=2600)
    d = _listing(session, "shopify-a", "Catan Deluxe", price=4000)

    service.merge(session, a.id, b.id)
    service.merge(session, c.id, d.id)
    payload = service.merge(session, b.id, c.id)

    assert payload["listing_count"] == 4
    assert len(session.exec(select(Game)).all()) == 1


def test_merge_keeps_the_game_hidden_if_either_was(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    _game(session, b).hidden = True
    session.commit()

    payload = service.merge(session, a.id, b.id)
    assert payload["game"].hidden is True


def test_merge_clears_an_earlier_rejection(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)

    service.reject(session, a.id, b.id)
    service.merge(session, a.id, b.id)
    assert session.exec(select(MergeRejection)).all() == []


def test_merge_rejects_self(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    r = client.post(f"/api/products/{a.id}/merge", json={"other_product_id": a.id})
    assert r.status_code == 400


def test_merge_404_for_missing_listing(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    r = client.post(f"/api/products/{a.id}/merge", json={"other_product_id": 4242})
    assert r.status_code == 404


def test_unmerge_gives_the_listing_its_own_game(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    service.merge(session, a.id, b.id)

    r = client.delete(f"/api/products/{a.id}/game")
    assert r.status_code == 200
    assert _game(session, a).id != _game(session, b).id
    assert r.json()["listing_count"] == 1


def test_unmerge_leaves_the_remaining_listings_together(
    client: TestClient, session: Session
):
    _stores(session)
    make_store(session, "woo-c", name="C", type="woocommerce")
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    c = _listing(session, "woo-c", "Catan Strategy Game", price=2600)
    service.merge(session, a.id, b.id)
    service.merge(session, b.id, c.id)

    service.unmerge(session, a.id)
    assert _game(session, b).id == _game(session, c).id
    assert _game(session, a).id not in {_game(session, b).id}


def test_unmerge_is_a_noop_for_a_single_listing_game(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    before = a.game_id
    assert client.delete(f"/api/products/{a.id}/game").status_code == 200
    assert _game(session, a).id == before


# --- comparison payload ---------------------------------------------------


def test_game_reports_cheapest_and_cheapest_in_stock(
    client: TestClient, session: Session
):
    _stores(session)
    cheap_oos = _listing(session, "shopify-a", "Catan", price=400, available=False)
    pricier = _listing(session, "woo-b", "Catan Board Game", price=600, available=True)
    payload = service.merge(session, cheap_oos.id, pricier.id)

    assert payload["cheapest"]["product_id"] == cheap_oos.id
    assert payload["cheapest"]["available"] is False
    assert payload["cheapest_in_stock"]["product_id"] == pricier.id
    assert payload["cheapest_in_stock"]["price"] == 600


def test_game_cheapest_in_stock_is_none_when_all_out_of_stock(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400, available=False)
    b = _listing(session, "woo-b", "Catan Board Game", price=600, available=False)
    payload = service.merge(session, a.id, b.id)

    assert payload["cheapest"]["product_id"] == a.id
    assert payload["cheapest_in_stock"] is None


def test_offers_respect_price_overrides(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400, available=True)
    b = _listing(session, "woo-b", "Catan Board Game", price=600, available=True)
    session.add(ProductOverride(product_id=a.id, override_price=900))
    session.commit()

    payload = service.merge(session, a.id, b.id)
    assert payload["cheapest"]["product_id"] == b.id


def test_identical_images_collapse(client: TestClient, session: Session):
    _stores(session)
    a = _listing(
        session, "shopify-a", "Catan", price=400, image_url="https://img/x.jpg"
    )
    b = _listing(
        session, "woo-b", "Catan Board Game", price=600, image_url="https://img/x.jpg"
    )
    assert len(service.merge(session, a.id, b.id)["images"]) == 1


def test_distinct_images_are_kept_cheapest_first(client: TestClient, session: Session):
    _stores(session)
    a = _listing(
        session, "shopify-a", "Catan", price=400, image_url="https://img/a.jpg"
    )
    b = _listing(
        session, "woo-b", "Catan Board Game", price=600, image_url="https://img/b.jpg"
    )
    payload = service.merge(session, a.id, b.id)
    assert [i["url"] for i in payload["images"]] == [
        "https://img/a.jpg",
        "https://img/b.jpg",
    ]


def test_series_carries_per_store_history(client: TestClient, session: Session):
    _stores(session)
    now = datetime.utcnow()
    a = _listing(
        session, "shopify-a", "Catan", price=3000, recorded_at=now - timedelta(days=2)
    )
    session.add(PriceSnapshot(product_id=a.id, price=2800, recorded_at=now))
    b = _listing(session, "woo-b", "Catan Board Game", price=2500, recorded_at=now)
    session.commit()

    payload = service.merge(session, a.id, b.id)
    by_store = {s["store_id"]: s for s in payload["series"]}
    assert [h["price"] for h in by_store["shopify-a"]["history"]] == [3000, 2800]
    assert len(by_store["woo-b"]["history"]) == 1


def test_game_endpoint_404s_for_unknown_game(client: TestClient):
    assert client.get("/api/games/999").status_code == 404


def test_absorbed_game_id_resolves_to_the_survivor(
    client: TestClient, session: Session
):
    """Merging retires one id; links to it must still land on the game."""
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    payload = service.merge(session, a.id, b.id)
    survivor = payload["game"].id
    absorbed = b.game_id if survivor == a.game_id else a.game_id

    r = client.get(f"/api/games/{absorbed}")
    assert r.status_code == 200
    assert r.json()["game"]["id"] == survivor


def test_merge_overwrites_a_stale_alias_for_a_reused_game_id(
    client: TestClient, session: Session
):
    """old_game_id is the alias table's primary key, and a game id can be
    reused after an earlier merge -- the row must be updated, not re-inserted."""
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    c = _listing(session, "woo-b", "Puerto Rico", price=1500)
    target_id, source_id = sorted([a.game_id, b.game_id])

    session.add(GameAlias(old_game_id=source_id, game_id=c.game_id))
    session.commit()

    payload = service.merge(session, a.id, b.id)

    alias = session.get(GameAlias, source_id)
    assert alias.game_id == target_id == payload["game"].id


def test_absorbed_id_follows_a_second_merge(client: TestClient, session: Session):
    _stores(session)
    make_store(session, "woo-c", name="C", type="woocommerce")
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    c = _listing(session, "woo-c", "Catan Strategy Game", price=2600)
    first = service.merge(session, b.id, c.id)
    absorbed = c.game_id if first["game"].id == b.game_id else b.game_id
    survivor = service.merge(session, a.id, b.id)["game"].id

    assert client.get(f"/api/games/{absorbed}").json()["game"]["id"] == survivor


def test_patching_an_absorbed_id_edits_the_survivor(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500)
    payload = service.merge(session, a.id, b.id)
    survivor = payload["game"].id
    absorbed = b.game_id if survivor == a.game_id else a.game_id

    r = client.patch(f"/api/games/{absorbed}", json={"title": "Catan (base)"})
    assert r.status_code == 200
    assert r.json()["game"]["id"] == survivor
    assert r.json()["game"]["title"] == "Catan (base)"


def test_game_for_listing_resolves_an_old_listing_url(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)
    r = client.get(f"/api/games/for-listing/{a.id}")
    assert r.json() == {"game_id": a.game_id, "store_id": "shopify-a"}


def test_game_rename_and_note(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000)

    r = client.patch(
        f"/api/games/{a.game_id}", json={"title": "Catan (base)", "note": "buy later"}
    )
    assert r.status_code == 200
    assert r.json()["game"]["title"] == "Catan (base)"
    assert r.json()["game"]["note"] == "buy later"
    assert (
        client.patch(f"/api/games/{a.game_id}", json={"title": " "}).status_code == 400
    )


# --- cards ----------------------------------------------------------------


def test_cards_expose_the_comparison(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400, available=False)
    b = _listing(session, "woo-b", "Catan Board Game", price=600, available=True)
    service.merge(session, a.id, b.id)

    card = repo.cards_by_ids(session, [a.id])[0]
    assert card["compare"]["listing_count"] == 2
    assert card["compare"]["cheapest"]["price"] == 400
    assert card["compare"]["cheapest_in_stock"]["price"] == 600
    history = card["compare"]["cheapest_in_stock"]["price_history"]
    assert [h["price"] for h in history] == [600.0]


def test_card_history_is_newest_first_with_timestamps(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(
        session,
        "shopify-a",
        "Catan",
        price=500,
        recorded_at=datetime(2026, 8, 10, 9, 0),
    )
    session.add(
        PriceSnapshot(
            product_id=a.id,
            price=400,
            available=True,
            recorded_at=datetime(2026, 8, 14, 9, 0),
        )
    )
    session.commit()

    history = repo.cards_by_ids(session, [a.id])[0]["price_history"]
    assert [h["price"] for h in history] == [400.0, 500.0]
    assert history[0]["recorded_at"] == datetime(2026, 8, 14, 9, 0)


def test_cards_have_no_comparison_for_a_single_shop(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    assert repo.cards_by_ids(session, [a.id])[0]["compare"] is None


def test_search_returns_a_merged_game_once(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    b = _listing(session, "woo-b", "Catan Board Game", price=600)
    service.merge(session, a.id, b.id)

    items = client.get("/api/search?q=catan").json()["items"]
    assert len(items) == 1


def test_hiding_a_listing_hides_the_game_everywhere(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    b = _listing(session, "woo-b", "Catan Board Game", price=600)
    service.merge(session, a.id, b.id)

    assert client.put(f"/api/products/{a.id}/hide").status_code == 200
    assert client.post("/api/browse/query", json={}).json()["items"] == []
    assert client.delete(f"/api/products/{b.id}/hide").status_code == 200
    items = client.post("/api/browse/query", json={}).json()["items"]
    assert len(items) == 1
    assert items[0]["compare"]["listing_count"] == 2


# --- watch + BGG follow the game -----------------------------------------


def test_watch_covers_every_listing_of_the_game(client: TestClient, session: Session):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    b = _listing(session, "woo-b", "Catan Board Game", price=600)
    service.merge(session, a.id, b.id)

    client.post("/api/watchlist/", json={"product_id": a.id})
    payload = client.get(f"/api/games/{_game(session, a).id}").json()
    assert payload["watchlist_item"] is not None
    # One watched game means one watchlist card, not one per shop.
    assert len(client.get("/api/watchlist/").json()) == 1


def test_merge_absorbs_a_watch_from_the_other_game(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    b = _listing(session, "woo-b", "Catan Board Game", price=600)
    client.post("/api/watchlist/", json={"product_id": b.id, "target_price": 500})

    service.merge(session, a.id, b.id)
    session.expire_all()
    active = session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()
    assert len(active) == 1
    assert active[0].game_id == _game(session, a).id
    assert active[0].target_price == 500


def test_merge_keeps_one_watch_when_both_games_were_watched(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=400)
    b = _listing(session, "woo-b", "Catan Board Game", price=600)
    client.post("/api/watchlist/", json={"product_id": a.id})
    client.post("/api/watchlist/", json={"product_id": b.id, "target_price": 300})
    watch_b = session.exec(
        select(WatchlistItem).where(WatchlistItem.game_id == b.game_id)
    ).one()
    session.add(
        WatchListingState(
            watch_id=watch_b.id, product_id=b.id, last_notified_price=600.0
        )
    )
    session.commit()

    service.merge(session, a.id, b.id)
    session.expire_all()
    active = session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()
    assert len(active) == 1
    # The survivor inherits the target and the alert memory, so nothing repeats.
    assert active[0].target_price == 300
    state = session.get(WatchListingState, (active[0].id, b.id))
    assert state is not None and state.last_notified_price == 600.0


def test_merge_inherits_the_bgg_link(client: TestClient, session: Session):
    _stores(session)
    linked = _listing(session, "shopify-a", "Catan", price=3000, bgg_id=13)
    unlinked = _listing(session, "woo-b", "Catan Board Game", price=2500)

    payload = service.merge(session, linked.id, unlinked.id)
    assert payload["game"].bgg_id == 13
    assert payload["discarded_bgg_id"] is None


def test_merge_reports_a_discarded_bgg_link_on_conflict(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000, bgg_id=13)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500, bgg_id=999)
    kept = min(a.game_id, b.game_id)
    kept_bgg = session.get(Game, kept).bgg_id

    payload = service.merge(session, a.id, b.id)
    assert payload["game"].bgg_id == kept_bgg
    assert payload["discarded_bgg_id"] == (999 if kept_bgg == 13 else 13)


def test_bgg_can_be_switched_to_the_discarded_link(
    client: TestClient, session: Session
):
    _stores(session)
    a = _listing(session, "shopify-a", "Catan", price=3000, bgg_id=13)
    b = _listing(session, "woo-b", "Catan Board Game", price=2500, bgg_id=999)
    payload = service.merge(session, a.id, b.id)

    r = client.patch(
        f"/api/games/{payload['game'].id}",
        json={"bgg_id": payload["discarded_bgg_id"]},
    )
    assert r.status_code == 200
    assert r.json()["game"]["bgg_id"] == payload["discarded_bgg_id"]
