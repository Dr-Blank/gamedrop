"""Several listing URLs per store: the endpoints that manage them, the detect
step that offers an existing store, and the sync that walks them all."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import Product, Store, StoreUrl
from app.scraper import sync_store


def _store_payload(**overrides):
    return {
        "id": "shop-a",
        "name": "Shop A",
        "type": "shopify",
        "base_url": "https://shop-a.com",
        "collection_path": "/collections/board-games",
        **overrides,
    }


def _create(client: TestClient, **overrides) -> dict:
    r = client.post("/api/stores/", json=_store_payload(**overrides))
    assert r.status_code == 200, r.text
    return r.json()


# --- managing a store's listing URLs ----------------------------------------


def test_creating_a_store_records_its_first_listing_url(client: TestClient):
    data = _create(client)
    assert [u["collection_path"] for u in data["urls"]] == ["/collections/board-games"]


def test_listing_stores_inlines_their_urls(client: TestClient):
    _create(client)
    client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/toys"}
    )

    stores = client.get("/api/stores/").json()
    assert [u["collection_path"] for u in stores[0]["urls"]] == [
        "/collections/board-games",
        "/collections/toys",
    ]


def test_add_a_second_url_to_an_existing_store(client: TestClient):
    _create(client)
    r = client.post(
        "/api/stores/shop-a/urls",
        json={"collection_path": "/collections/puzzles", "label": "Puzzles"},
    )
    assert r.status_code == 200
    assert r.json()["collection_path"] == "/collections/puzzles"
    assert r.json()["label"] == "Puzzles"
    assert r.json()["enabled"] is True


def test_reject_a_path_the_store_already_syncs(client: TestClient):
    _create(client)
    r = client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/board-games"}
    )
    assert r.status_code == 409


def test_a_trailing_slash_is_the_same_page(client: TestClient):
    _create(client)
    r = client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/board-games/"}
    )
    assert r.status_code == 409


def test_blank_path_means_the_whole_catalog(client: TestClient):
    _create(client)
    r = client.post("/api/stores/shop-a/urls", json={"collection_path": ""})
    assert r.json()["collection_path"] == "/"


def test_reject_a_path_without_a_leading_slash(client: TestClient):
    _create(client)
    r = client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "collections/toys"}
    )
    assert r.status_code == 422


def test_add_url_to_a_store_that_does_not_exist(client: TestClient):
    r = client.post("/api/stores/nope/urls", json={"collection_path": "/x"})
    assert r.status_code == 404


def test_edit_a_listing_url(client: TestClient):
    _create(client)
    url_id = client.get("/api/stores/shop-a/urls").json()[0]["id"]

    r = client.patch(
        f"/api/stores/shop-a/urls/{url_id}",
        json={"collection_path": "/collections/all", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["collection_path"] == "/collections/all"
    assert r.json()["enabled"] is False


def test_editing_a_url_onto_a_path_the_store_already_syncs(client: TestClient):
    _create(client)
    other = client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/toys"}
    ).json()

    r = client.patch(
        f"/api/stores/shop-a/urls/{other['id']}",
        json={"collection_path": "/collections/board-games"},
    )
    assert r.status_code == 409
    assert (
        client.get("/api/stores/shop-a/urls").json()[1]["collection_path"]
        == "/collections/toys"
    )


def test_delete_a_listing_url(client: TestClient):
    _create(client)
    extra = client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/toys"}
    ).json()

    assert client.delete(f"/api/stores/shop-a/urls/{extra['id']}").status_code == 200
    assert len(client.get("/api/stores/shop-a/urls").json()) == 1


def test_a_url_belongs_to_one_store_only(client: TestClient):
    _create(client)
    _create(client, id="shop-b", base_url="https://shop-b.com")
    url_id = client.get("/api/stores/shop-a/urls").json()[0]["id"]

    assert client.patch(f"/api/stores/shop-b/urls/{url_id}", json={}).status_code == 404
    assert client.delete(f"/api/stores/shop-b/urls/{url_id}").status_code == 404


def test_removing_a_store_removes_its_urls(client: TestClient, session: Session):
    _create(client)
    client.post(
        "/api/stores/shop-a/urls", json={"collection_path": "/collections/toys"}
    )

    client.delete("/api/stores/shop-a")

    assert session.exec(select(StoreUrl)).all() == []


# --- detect offers the store a pasted URL belongs to -------------------------


@pytest.fixture(name="no_probe")
def no_probe_fixture():
    """Skip the network probe; these tests are about what detect reports back."""
    with patch(
        "app.routes.stores.detect_platform",
        return_value={"type": "shopify", "sample_titles": []},
    ):
        yield


def test_detect_names_the_store_already_on_that_host(client: TestClient, no_probe):
    _create(client)

    r = client.post(
        "/api/stores/detect",
        json={"base_url": "https://www.shop-a.com/collections/puzzles"},
    )
    assert r.json()["matches"] == ["shop-a"]


def test_detect_reports_no_match_for_an_unknown_host(client: TestClient, no_probe):
    _create(client)

    r = client.post("/api/stores/detect", json={"base_url": "https://other.com"})
    assert r.json()["matches"] == []


def test_detect_splits_the_pasted_path_off_the_shop_url(client: TestClient, no_probe):
    r = client.post(
        "/api/stores/detect",
        json={"base_url": "https://shop-a.com/collections/puzzles/"},
    ).json()

    assert r["base_url"] == "https://shop-a.com"
    assert r["collection_path"] == "/collections/puzzles"


def test_detect_falls_back_to_the_platform_default_path(client: TestClient, no_probe):
    r = client.post(
        "/api/stores/detect", json={"base_url": "https://shop-a.com"}
    ).json()

    assert r["collection_path"] == "/collections/board-games"


# --- syncing every configured URL -------------------------------------------


def _listing(external_id: str, price: float = 500.0) -> dict:
    return {
        "external_id": external_id,
        "title": external_id,
        "handle": external_id,
        "url": f"https://shop-a.com/products/{external_id}",
        "image_url": None,
        "variants": [
            {
                "variant_id": f"v-{external_id}",
                "variant_title": "Default",
                "price": price,
                "compare_at_price": None,
                "available": True,
            }
        ],
    }


class _PathAdapter:
    """Serves a different catalog per listing path, like overlapping categories."""

    def __init__(self, by_path: dict[str, list[dict]]):
        self.by_path = by_path
        self.walked: list[str] = []

    def __call__(self, store, collection_path="/"):
        self.walked.append(collection_path)
        self.path = collection_path
        return self

    async def fetch_products(self):
        payload = self.by_path[self.path]
        if isinstance(payload, Exception):
            raise payload
        return payload


def _store_with_paths(session: Session, *paths: str) -> Store:
    store = Store(
        id="shop-a", name="Shop A", type="shopify", base_url="https://shop-a.com"
    )
    session.add(store)
    for path in paths:
        session.add(StoreUrl(store_id="shop-a", collection_path=path))
    session.commit()
    session.refresh(store)
    return store


def _sync(store: Store, adapter: _PathAdapter) -> dict:
    with patch("app.scraper.get_adapter", adapter):
        return asyncio.run(sync_store(store))


def test_sync_walks_every_configured_url(session: Session):
    store = _store_with_paths(session, "/collections/a", "/collections/b")
    adapter = _PathAdapter(
        {"/collections/a": [_listing("e1")], "/collections/b": [_listing("e2")]}
    )

    result = _sync(store, adapter)

    assert adapter.walked == ["/collections/a", "/collections/b"]
    assert result["new_products"] == 2
    assert {p.external_id for p in session.exec(select(Product)).all()} == {"e1", "e2"}


def test_a_listing_in_two_categories_is_recorded_once(session: Session):
    """Categories overlap, and one shop listing is still one listing."""
    store = _store_with_paths(session, "/collections/a", "/collections/b")
    adapter = _PathAdapter(
        {"/collections/a": [_listing("e1")], "/collections/b": [_listing("e1")]}
    )

    result = _sync(store, adapter)

    assert result["new_products"] == 1
    assert len(session.exec(select(Product)).all()) == 1


def test_sync_skips_a_disabled_url(session: Session):
    store = _store_with_paths(session, "/collections/a", "/collections/b")
    disabled = session.exec(
        select(StoreUrl).where(StoreUrl.collection_path == "/collections/b")
    ).one()
    disabled.enabled = False
    session.add(disabled)
    session.commit()

    adapter = _PathAdapter({"/collections/a": [_listing("e1")]})
    _sync(store, adapter)

    assert adapter.walked == ["/collections/a"]


def test_sync_reports_which_url_failed(session: Session):
    store = _store_with_paths(session, "/collections/a", "/collections/b")
    adapter = _PathAdapter(
        {
            "/collections/a": [_listing("e1")],
            "/collections/b": RuntimeError("503 down"),
        }
    )

    with pytest.raises(RuntimeError, match="503 down"):
        _sync(store, adapter)

    session.expire_all()
    assert "/collections/b" in session.get(Store, "shop-a").last_sync_error


def test_sync_refuses_a_store_with_no_urls(session: Session):
    store = _store_with_paths(session)

    with pytest.raises(ValueError, match="no listing URLs"):
        _sync(store, _PathAdapter({}))

    session.expire_all()
    assert session.get(Store, "shop-a").last_sync_error == "no listing URLs configured"


def test_a_failing_store_does_not_cost_the_others_their_sync(session: Session):
    from app.scraper import sync_all_stores

    _store_with_paths(session, "/collections/a")
    ok = Store(
        id="shop-b", name="Shop B", type="shopify", base_url="https://shop-b.com"
    )
    session.add(ok)
    session.add(StoreUrl(store_id="shop-b", collection_path="/collections/b"))
    session.commit()

    adapter = _PathAdapter(
        {"/collections/a": RuntimeError("503 down"), "/collections/b": [_listing("e2")]}
    )
    with patch("app.scraper.get_adapter", adapter):
        asyncio.run(sync_all_stores())

    session.expire_all()
    assert session.get(Store, "shop-b").last_sync_error is None
    assert [p.store_id for p in session.exec(select(Product)).all()] == ["shop-b"]
