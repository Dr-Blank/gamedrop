"""WooCommerce Store API adapter. HTTP is served by an httpx MockTransport."""

import asyncio
from functools import partial

import httpx
import pytest
from sqlmodel import Session

from app.adapters import woocommerce as woo
from app.adapters.woocommerce import WooCommerceAdapter, category_slug, map_product
from app.models import Store
from app.scraper import get_adapter

CATEGORIES = [
    {"id": 77, "slug": "puzzles-and-board-games", "name": "Puzzles & Board Games"},
    {"id": 230, "slug": "board-games", "name": "Board Games", "parent": 77},
]


def _product(**overrides):
    product = {
        "id": 54480,
        "name": "Catan &#8211; Strategy Game | Ages 10+",
        "slug": "catan-strategy-game",
        "type": "simple",
        "permalink": "https://shop.test/product/catan-strategy-game/",
        "prices": {
            "price": "425000",
            "regular_price": "599000",
            "sale_price": "425000",
            "price_range": None,
            "currency_code": "INR",
            "currency_minor_unit": 2,
        },
        "images": [{"src": "https://shop.test/catan.jpg"}],
        "is_in_stock": True,
        "is_purchasable": True,
        "is_on_backorder": False,
    }
    product.update(overrides)
    return product


def _store(session: Session | None = None, **overrides) -> Store:
    store = Store(
        id="woo",
        name="Woo Shop",
        type="woocommerce",
        base_url="https://shop.test",
        collection_path="/product-category/puzzles-and-board-games/",
        scrape_config='{"timeout_sec":5,"request_delay_sec":0}',
    )
    for key, value in overrides.items():
        setattr(store, key, value)
    if session is not None:
        session.add(store)
        session.commit()
    return store


def _mock_client(monkeypatch, handler):
    """Point the adapter's httpx client at an in-process transport."""
    monkeypatch.setattr(
        woo.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


def _pages_handler(pages: dict[int, list[dict]], calls: list | None = None):
    """Serve the categories route plus a page → products mapping."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path.endswith("/products/categories"):
            return httpx.Response(200, json=CATEGORIES)
        page = int(request.url.params.get("page", 1))
        batch = pages.get(page, [])
        return httpx.Response(
            200,
            json=batch,
            headers={"x-wp-totalpages": str(max(pages, default=1))},
        )

    return handler


# --- title / price mapping ---------------------------------------------------


def test_map_product_converts_minor_unit_prices():
    mapped = map_product(_product())
    variant = mapped["variants"][0]
    assert variant["price"] == 4250.0
    assert variant["compare_at_price"] == 5990.0


def test_map_product_unescapes_title_and_keeps_marketing_tail():
    mapped = map_product(_product())
    assert mapped["title"] == "Catan – Strategy Game | Ages 10+"


def test_map_product_uses_first_image_and_permalink():
    mapped = map_product(_product())
    assert mapped["image_url"] == "https://shop.test/catan.jpg"
    assert mapped["url"] == "https://shop.test/product/catan-strategy-game/"
    assert mapped["handle"] == "catan-strategy-game"
    assert mapped["external_id"] == "54480"


def test_map_product_no_compare_at_when_not_discounted():
    raw = _product()
    raw["prices"]["regular_price"] = "425000"
    assert map_product(raw)["variants"][0]["compare_at_price"] is None


def test_map_product_out_of_stock():
    assert map_product(_product(is_in_stock=False))["variants"][0]["available"] is False


def test_map_product_backorder_counts_as_unavailable():
    raw = _product(is_in_stock=True, is_on_backorder=True)
    assert map_product(raw)["variants"][0]["available"] is False


def test_map_product_variable_uses_low_end_of_range():
    raw = _product(type="variable")
    raw["prices"]["price"] = "199000"
    raw["prices"]["price_range"] = {"min_amount": "199000", "max_amount": "299000"}
    assert map_product(raw)["variants"][0]["price"] == 1990.0


def test_map_product_skips_priceless_rows():
    raw = _product()
    raw["prices"]["price"] = ""
    assert map_product(raw) is None


def test_map_product_handles_zero_minor_unit():
    raw = _product()
    raw["prices"] = {"price": "4250", "regular_price": "4250", "currency_minor_unit": 0}
    assert map_product(raw)["variants"][0]["price"] == 4250.0


# --- category path parsing ---------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/product-category/puzzles-and-board-games/", "puzzles-and-board-games"),
        ("/product-category/parent/child/", "child"),
        ("/board-games", "board-games"),
        ("/", None),
        ("", None),
        (None, None),
    ],
)
def test_category_slug(path, expected):
    assert category_slug(path) == expected


# --- fetch_products ---------------------------------------------------------


def test_fetch_products_resolves_category_and_maps_rows(monkeypatch):
    calls: list[str] = []
    _mock_client(monkeypatch, _pages_handler({1: [_product()]}, calls))

    products = asyncio.run(WooCommerceAdapter(_store()).fetch_products())

    assert len(products) == 1
    assert products[0]["variants"][0]["price"] == 4250.0
    listing_call = next(c for c in calls if "categories" not in c)
    assert "category=77" in listing_call
    assert "per_page=100" in listing_call


def test_fetch_products_syncs_whole_catalog_without_category(monkeypatch):
    calls: list[str] = []
    _mock_client(monkeypatch, _pages_handler({1: [_product()]}, calls))

    store = _store(collection_path="/")
    asyncio.run(WooCommerceAdapter(store).fetch_products())

    assert not any("categories" in c for c in calls)
    assert not any("category=" in c for c in calls)


def test_fetch_products_pages_until_short_batch(monkeypatch):
    full_page = [_product(id=i, slug=f"p{i}") for i in range(woo.PER_PAGE)]
    pages = {1: full_page, 2: [_product(id=999, slug="last")]}
    _mock_client(monkeypatch, _pages_handler(pages))

    products = asyncio.run(WooCommerceAdapter(_store()).fetch_products())

    assert len(products) == woo.PER_PAGE + 1
    assert products[-1]["external_id"] == "999"


def test_fetch_products_raises_when_category_missing(monkeypatch):
    _mock_client(monkeypatch, _pages_handler({1: []}))
    store = _store(collection_path="/product-category/nope/")

    with pytest.raises(ValueError, match="category not found"):
        asyncio.run(WooCommerceAdapter(store).fetch_products())


def test_fetch_products_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/products/categories"):
            return httpx.Response(200, json=CATEGORIES)
        return httpx.Response(503, text="down")

    _mock_client(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(WooCommerceAdapter(_store()).fetch_products())


def test_fetch_product_image(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/products/54480")
        return httpx.Response(200, json=_product())

    _mock_client(monkeypatch, handler)

    class _P:
        external_id = "54480"

    assert (
        asyncio.run(WooCommerceAdapter(_store()).fetch_product_image(_P()))
        == "https://shop.test/catan.jpg"
    )


# --- wiring ----------------------------------------------------------------


def test_get_adapter_returns_woocommerce_adapter():
    assert isinstance(get_adapter(_store()), WooCommerceAdapter)


def test_create_woocommerce_store(client):
    r = client.post(
        "/api/stores/",
        json={
            "id": "befikar",
            "name": "Shop Befikar",
            "type": "woocommerce",
            "base_url": "https://shopbefikar.com",
            "collection_path": "/product-category/puzzles-and-board-games/",
        },
    )
    assert r.status_code == 200
    assert r.json()["type"] == "woocommerce"


def test_create_store_rejects_unknown_type(client):
    r = client.post(
        "/api/stores/",
        json={
            "id": "weird",
            "name": "Weird",
            "type": "magento",
            "base_url": "https://weird.test",
        },
    )
    assert r.status_code == 422
