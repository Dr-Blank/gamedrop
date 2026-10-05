"""Wix Stores gallery adapter. HTTP is served by an httpx MockTransport."""

import asyncio
import json
from functools import partial

import httpx
import pytest

from app.adapters import detect, wix
from app.adapters.detect import detect_platform
from app.adapters.wix import WixAdapter, find_gallery, map_product
from app.models import Store
from app.scraper import get_adapter

STORES_APP = "1380b703-ce81-ff05-f115-39571d94dfcd"


def _product(**overrides):
    product = {
        "id": "b998895f-756c-69aa-1f29-b23f205c7a5c",
        "name": "Catan Board Game ",
        "urlPart": "catan-board-game",
        "price": 3500,
        "comparePrice": 0,
        "isInStock": True,
        "currency": "INR",
        "media": [
            {
                "url": "abc~mv2.png",
                "fullUrl": "https://static.wixstatic.com/media/abc~mv2.png/v1/fit/file.png",
            }
        ],
    }
    product.update(overrides)
    return product


def _page(products: list[dict], total: int | None = None) -> str:
    warmup = {
        "appsWarmupData": {
            "dataBinding": {},
            STORES_APP: {
                "initialData_default_TPASection_x_default": {
                    "appSettings": {},
                    "catalog": {
                        "category": {
                            "name": "All Products",
                            "productsWithMetaData": {
                                "list": products,
                                "totalCount": len(products) if total is None else total,
                            },
                        }
                    },
                }
            },
        }
    }
    return (
        "<html><head></head><body>"
        '<script type="application/json" id="wix-viewer-model">{}</script>'
        '<script type="application/json" id="wix-warmup-data">'
        f"{json.dumps(warmup)}</script></body></html>"
    )


def _store(**overrides) -> Store:
    store = Store(
        id="wixshop",
        name="Wix Shop",
        type="wix",
        base_url="https://shop.test",
        scrape_config='{"timeout_sec":5,"request_delay_sec":0}',
    )
    for key, value in overrides.items():
        setattr(store, key, value)
    return store


def _adapter(collection_path: str = "/shop") -> WixAdapter:
    return WixAdapter(_store(), collection_path)


def _mock_client(monkeypatch, module, handler):
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


def _catalog(n: int) -> list[dict]:
    return [_product(id=f"id-{i}", urlPart=f"game-{i}") for i in range(n)]


def _gallery_handler(catalog: list[dict], page_size: int, calls: list | None = None):
    """Serve a gallery that renders `page` pages cumulatively, like Wix does."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url)
        pages = int(request.url.params.get("page", 1))
        return httpx.Response(
            200, text=_page(catalog[: pages * page_size], total=len(catalog))
        )

    return handler


# --- gallery parsing ---------------------------------------------------------


def test_find_gallery_reads_products_and_total():
    gallery = find_gallery(_page([_product()], total=40))
    assert gallery["totalCount"] == 40
    assert gallery["list"][0]["urlPart"] == "catan-board-game"


@pytest.mark.parametrize(
    "page_html",
    [
        "<html>no data</html>",
        '<script type="application/json" id="wix-warmup-data">{bad</script>',
        '<script type="application/json" id="wix-warmup-data">'
        '{"appsWarmupData": {"other": {"w": {"foo": 1}}}}</script>',
    ],
)
def test_find_gallery_none_without_a_gallery(page_html):
    assert find_gallery(page_html) is None


# --- product mapping ---------------------------------------------------------


def test_map_product_full_price():
    mapped = map_product(_product(), "https://shop.test")
    assert mapped["external_id"] == "b998895f-756c-69aa-1f29-b23f205c7a5c"
    assert mapped["title"] == "Catan Board Game"
    assert mapped["url"] == "https://shop.test/product-page/catan-board-game"
    assert mapped["handle"] == "catan-board-game"
    assert mapped["image_url"].startswith("https://static.wixstatic.com/media/abc")
    variant = mapped["variants"][0]
    assert variant["price"] == 3500.0
    assert variant["compare_at_price"] is None
    assert variant["available"] is True


def test_map_product_compare_price_is_the_sale_price():
    variant = map_product(_product(price=3500, comparePrice=2500), "https://s")[
        "variants"
    ][0]
    assert variant["price"] == 2500.0
    assert variant["compare_at_price"] == 3500.0


def test_map_product_out_of_stock():
    mapped = map_product(_product(isInStock=False), "https://s")
    assert mapped["variants"][0]["available"] is False


def test_map_product_skips_priceless_rows():
    assert map_product(_product(price=None), "https://s") is None


def test_map_product_without_media_or_slug():
    mapped = map_product(_product(media=[], urlPart=None), "https://s")
    assert mapped["image_url"] is None
    assert mapped["url"] is None


# --- fetch_products ---------------------------------------------------------


def test_fetch_products_single_page_makes_one_request(monkeypatch):
    calls: list = []
    _mock_client(monkeypatch, wix, _gallery_handler(_catalog(5), 20, calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 5
    assert len(calls) == 1
    assert calls[0].path == "/shop"


def test_fetch_products_renders_every_page_in_one_more_request(monkeypatch):
    calls: list = []
    _mock_client(monkeypatch, wix, _gallery_handler(_catalog(45), 20, calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 45
    assert len(calls) == 2
    assert calls[1].params["page"] == "3"


def test_fetch_products_dedupes_repeated_rows(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_page([_product(), _product()]))

    _mock_client(monkeypatch, wix, handler)
    assert len(asyncio.run(_adapter().fetch_products())) == 1


def test_fetch_products_raises_without_gallery(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html></html>")

    _mock_client(monkeypatch, wix, handler)
    with pytest.raises(ValueError, match="no product gallery"):
        asyncio.run(_adapter("/about").fetch_products())


def test_fetch_products_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    _mock_client(monkeypatch, wix, handler)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_adapter().fetch_products())


# --- detection ----------------------------------------------------------------


def _wix_site_handler(request: httpx.Request) -> httpx.Response:
    headers = {"x-wix-request-id": "1"}
    if request.url.path == "/shop":
        return httpx.Response(200, text=_page(_catalog(5)), headers=headers)
    return httpx.Response(404, text="not found", headers=headers)


def test_detect_platform_finds_wix_with_samples(monkeypatch):
    _mock_client(monkeypatch, detect, _wix_site_handler)

    result = asyncio.run(detect_platform("https://shop.test"))

    assert result["type"] == "wix"
    assert len(result["sample_titles"]) == 3


def test_detect_platform_wix_without_shop_page(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"x-wix-request-id": "1"})

    _mock_client(monkeypatch, detect, handler)

    result = asyncio.run(detect_platform("https://shop.test"))

    assert result["type"] == "wix"
    assert result["sample_titles"] == []


def test_detect_platform_unknown_without_wix_header(monkeypatch):
    _mock_client(monkeypatch, detect, lambda request: httpx.Response(404))
    assert asyncio.run(detect_platform("https://shop.test"))["type"] is None


# --- wiring ----------------------------------------------------------------


def test_get_adapter_returns_wix_adapter():
    assert isinstance(get_adapter(_store()), WixAdapter)


def test_create_wix_store_defaults_to_shop_path(client):
    r = client.post(
        "/api/stores/",
        json={"type": "wix", "base_url": "https://wixshop.test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "wix"
    assert [u["collection_path"] for u in body["urls"]] == ["/shop"]
