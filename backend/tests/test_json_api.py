"""Generic JSON API adapter and its discovery. HTTP is an httpx MockTransport."""

import asyncio
import json
from functools import partial

import httpx
import pytest

from app.adapters import detect, json_api
from app.adapters.detect import detect_platform
from app.adapters.json_api import (
    JsonApiAdapter,
    collection_params,
    get_path,
    map_item,
    normalize_config,
    to_num,
    truthy,
)
from app.adapters.json_api_discover import (
    discover,
    find_items_path,
    find_total_path,
    guess_fields,
    guess_url_template,
)
from app.models import Store
from app.scraper import get_adapter

BASE = "https://shop.test"

SCRIPT = """
fetch("/api/products?"+q);
const a=`/collections/${c.slug}`, b=`/collections/${d.slug}`;
const p=`/products/${e.slug}`;
"""

HOME = """<html><head><script src="/_next/app.js"></script>
<script src="https://cdn.other.test/x.js"></script></head>
<body><a href="/collections/strategy">Strategy</a></body></html>"""


def _item(i: int, **over) -> dict:
    return {
        "id": f"p{i}",
        "name": f"Game {i}",
        "slug": f"game-{i}",
        "price": 1000 + i,
        "comparePrice": 2000 + i,
        "stock": i % 2,
        "isPreOrder": False,
        "images": [f"https://img.test/{i}.webp"],
        "categories": [{"slug": "strategy" if i % 3 == 0 else "family"}],
        **over,
    }


CATALOG = [_item(i) for i in range(1, 251)]


def _api(request: httpx.Request, cap: int = 100, style: str = "offset"):
    """A product list paged by offset/limit or page/limit, capped at `cap`."""
    q = request.url.params
    items = CATALOG
    if "category" in q:
        items = [p for p in items if p["categories"][0]["slug"] == q["category"]]
    limit = min(int(q.get("limit", 20)), cap)
    if style == "offset":
        start = int(q.get("offset", 0))
    else:
        start = (int(q.get("page", 1)) - 1) * limit
    page = items[start : start + limit]
    return httpx.Response(
        200, json={"products": page, "total": len(items), "limit": limit}
    )


def _site(request: httpx.Request, **kw):
    path = request.url.path
    if path == "/":
        return httpx.Response(200, text=HOME)
    if path == "/_next/app.js":
        return httpx.Response(200, text=SCRIPT)
    if path == "/api/products":
        return _api(request, **kw)
    return httpx.Response(404, text="nope")


def _mock_client(monkeypatch, handler):
    monkeypatch.setattr(
        json_api.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


CFG = normalize_config(
    {
        "endpoint": "/api/products",
        "items_path": "products",
        "total_path": "total",
        "paging": "offset",
        "page_param": "offset",
        "size_param": "limit",
        "page_size": 100,
        "collection_param": "category",
        "fields": {
            "id": "id",
            "title": "name",
            "price": "price",
            "compare_at": "comparePrice",
            "available": "stock",
            "preorder": "isPreOrder",
            "image": "images.0",
            "handle": "slug",
            "url": "/products/{slug}",
        },
    }
)


def _store(cfg: dict = CFG) -> Store:
    return Store(
        id="s",
        name="S",
        type="json_api",
        base_url=BASE,
        scrape_config=json.dumps({"request_delay_sec": 0, "json_api": cfg}),
    )


def _fetch(monkeypatch, handler, cfg=CFG, path="/") -> list[dict]:
    _mock_client(monkeypatch, handler)
    return asyncio.run(JsonApiAdapter(_store(cfg), path).fetch_products())


# --- helpers -----------------------------------------------------------------


def test_get_path_walks_dicts_and_lists():
    body = {"data": {"items": [{"img": {"url": "u"}}]}}
    assert get_path(body, "data.items.0.img.url") == "u"
    assert get_path(body, "data.items.5") is None
    assert get_path(body, "data.nope.x") is None
    assert get_path(body, "") is body


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (3, True),
        (0, False),
        ("instock", True),
        ("In Stock", True),
        ("outofstock", False),
        ("2", True),
        (None, False),
    ],
)
def test_truthy_reads_stock_values(value, expected):
    assert truthy(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Rs. 499", 499.0), ("₹1,299.50", 1299.5), ("-5", -5.0), ("free", None)],
)
def test_to_num_reads_the_first_number(value, expected):
    assert to_num(value) == expected


def test_collection_params():
    assert collection_params(CFG, "/") == {}
    assert collection_params(CFG, "/shop") == {}
    assert collection_params(CFG, "/collections/strategy") == {"category": "strategy"}
    assert collection_params(CFG, "/shop?badge=new") == {"badge": "new"}
    no_param = {**CFG, "collection_param": ""}
    assert collection_params(no_param, "/collections/strategy") == {}


# --- mapping -----------------------------------------------------------------


def test_map_item_reads_the_configured_fields():
    m = map_item(_item(1), CFG, BASE)
    assert m["external_id"] == "p1"
    assert m["title"] == "Game 1"
    assert m["handle"] == "game-1"
    assert m["url"] == f"{BASE}/products/game-1"
    assert m["image_url"] == "https://img.test/1.webp"
    v = m["variants"][0]
    assert (v["price"], v["compare_at_price"]) == (1001.0, 2001.0)
    assert (v["available"], v["preorder"]) == (True, False)


def test_map_item_out_of_stock():
    v = map_item(_item(2), CFG, BASE)["variants"][0]
    assert (v["available"], v["preorder"]) == (False, False)


def test_map_item_preorder_is_available():
    v = map_item(_item(2, isPreOrder=True), CFG, BASE)["variants"][0]
    assert (v["available"], v["preorder"]) == (True, True)


def test_map_item_drops_compare_at_not_above_price():
    item = _item(1, comparePrice=500)
    assert map_item(item, CFG, BASE)["variants"][0]["compare_at_price"] is None


def test_map_item_sale_price_moves_price_to_compare_at():
    cfg = normalize_config({**CFG, "fields": {**CFG["fields"], "sale_price": "sale"}})
    item = _item(1, price=3000, sale="₹2,499.00", comparePrice=None)
    v = map_item(item, cfg, BASE)["variants"][0]
    assert (v["price"], v["compare_at_price"]) == (2499.0, 3000.0)


def test_map_item_divides_minor_units():
    cfg = {**CFG, "price_divisor": 100}
    v = map_item(_item(1, price=129900, comparePrice=None), cfg, BASE)["variants"][0]
    assert v["price"] == 1299.0


def test_map_item_without_stock_field_is_available():
    cfg = normalize_config({**CFG, "fields": {**CFG["fields"], "available": ""}})
    assert map_item(_item(2), cfg, BASE)["variants"][0]["available"] is True


def test_map_item_url_field_joins_relative_links():
    cfg = normalize_config({**CFG, "fields": {**CFG["fields"], "url": "link"}})
    assert map_item(_item(1, link="/p/1"), cfg, BASE)["url"] == f"{BASE}/p/1"


def test_map_item_drops_non_http_links_and_images():
    cfg = normalize_config({**CFG, "fields": {**CFG["fields"], "url": "link"}})
    item = _item(1, link="javascript:alert(1)", images=["data:text/html,x"])
    m = map_item(item, cfg, BASE)
    assert (m["url"], m["image_url"]) == (None, None)


@pytest.mark.parametrize("over", [{"price": None}, {"price": "call us"}, {"id": None}])
def test_map_item_skips_items_without_id_or_price(over):
    assert map_item(_item(1, **over), CFG, BASE) is None


# --- fetching ----------------------------------------------------------------


def test_fetch_walks_every_offset_page_past_a_server_cap(monkeypatch):
    products = _fetch(monkeypatch, partial(_site, cap=40))
    assert len(products) == 250
    assert len({p["external_id"] for p in products}) == 250


def test_fetch_walks_page_numbers(monkeypatch):
    cfg = {**CFG, "paging": "page", "page_param": "page", "first_page": 1}
    products = _fetch(monkeypatch, partial(_site, style="page"), cfg)
    assert len(products) == 250


def test_fetch_stops_when_the_server_ignores_paging(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"products": CATALOG[:10]})

    products = _fetch(monkeypatch, handler, {**CFG, "total_path": ""})
    assert len(products) == 10
    assert len(calls) == 2


def test_fetch_offsets_by_items_fetched_not_kept(monkeypatch):
    listing = [*CATALOG[:50], CATALOG[0]]
    calls = []

    def handler(request):
        calls.append(request)
        start = int(request.url.params.get("offset", 0))
        page = listing[start : start + 20]
        return httpx.Response(200, json={"products": page, "total": len(listing)})

    products = _fetch(monkeypatch, handler)
    assert len(products) == 50
    assert [int(c.url.params["offset"]) for c in calls] == [0, 20, 40]


def test_fetch_filters_by_collection_path(monkeypatch):
    products = _fetch(monkeypatch, _site, path="/collections/strategy")
    assert len(products) == len(
        [p for p in CATALOG if p["categories"][0]["slug"] == "strategy"]
    )


def test_fetch_without_endpoint_raises(monkeypatch):
    with pytest.raises(ValueError, match="no endpoint"):
        _fetch(monkeypatch, _site, normalize_config(None))


def test_fetch_raises_when_items_path_is_wrong(monkeypatch):
    with pytest.raises(ValueError, match="no item list"):
        _fetch(monkeypatch, _site, {**CFG, "items_path": "data"})


# --- discovery ---------------------------------------------------------------


def test_find_items_path_nested():
    body = {"meta": {}, "data": {"items": [_item(1)]}}
    assert find_items_path(body) == "data.items"
    assert find_items_path([_item(1)]) == ""
    assert find_items_path({"rows": [{"a": 1}]}) is None


def test_find_total_path_ignores_a_page_count():
    assert find_total_path({"products": [], "count": 20}, "products") == ""
    assert find_total_path({"meta": {"total": 250}, "items": []}, "items") == (
        "meta.total"
    )


def test_guess_fields_handles_nested_prices_and_images():
    items = [
        {
            "_id": "a",
            "title": "T",
            "price": {"amount": 10},
            "images": [{"src": "x.png"}],
            "handle": "t",
        }
    ]
    fields = guess_fields(items)
    assert fields["id"] == "_id"
    assert fields["price"] == "price.amount"
    assert fields["image"] == "images.0.src"
    assert fields["url"] == "/products/{handle}"


def test_guess_fields_nested_price_when_first_item_lacks_it():
    items = [
        {"id": "a", "name": "A", "price": None},
        {"id": "b", "name": "B", "price": {"amount": 10}},
        {"id": "c", "name": "C", "price": {"amount": 12}},
    ]
    assert guess_fields(items)["price"] == "price.amount"


def test_url_template_prefers_product_routes():
    assert guess_url_template([SCRIPT], "slug") == "/products"


def test_discover_guesses_a_working_config(monkeypatch):
    _mock_client(monkeypatch, _site)

    async def run():
        async with httpx.AsyncClient() as client:
            return await discover(client, BASE)

    cfg = asyncio.run(run())
    assert cfg["endpoint"] == "/api/products"
    assert (cfg["items_path"], cfg["total_path"]) == ("products", "total")
    assert (cfg["paging"], cfg["page_param"], cfg["size_param"]) == (
        "offset",
        "offset",
        "limit",
    )
    assert cfg["collection_param"] == "category"
    assert cfg["fields"] == {**CFG["fields"], "sale_price": ""}


def test_discover_uses_a_pasted_api_url(monkeypatch):
    def handler(request):
        if request.url.path == "/v9/catalog":
            return httpx.Response(200, json={"data": {"items": CATALOG[:5]}})
        return httpx.Response(200, text="<html/>")

    _mock_client(monkeypatch, handler)

    async def run():
        async with httpx.AsyncClient() as client:
            return await discover(client, BASE, f"{BASE}/v9/catalog?limit=5")

    cfg = asyncio.run(run())
    assert cfg["endpoint"] == "/v9/catalog"
    assert cfg["items_path"] == "data.items"
    assert cfg["paging"] == "none"


def test_detect_platform_falls_back_to_json_api(monkeypatch):
    _mock_client(monkeypatch, _site)
    result = asyncio.run(detect_platform(BASE))
    assert result["type"] == "json_api"
    assert result["sample_titles"] == ["Game 1", "Game 2", "Game 3"]
    assert result["json_api"]["config"]["endpoint"] == "/api/products"
    assert result["json_api"]["warnings"] == []


def test_detect_platform_gives_up_on_slow_discovery(monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(404))

    async def slow(*_args, **_kw):
        await asyncio.sleep(1)

    monkeypatch.setattr(detect, "inspect_json_api", slow)
    monkeypatch.setattr(detect, "DISCOVERY_BUDGET", 0.01)
    assert asyncio.run(detect_platform(BASE))["type"] is None


def test_inspect_route_tolerates_non_string_field_paths(client, monkeypatch):
    _mock_client(monkeypatch, _site)
    r = client.post(
        "/api/stores/json-api/inspect",
        json={
            "base_url": BASE,
            "config": {**CFG, "fields": {**CFG["fields"], "id": 1}},
        },
    )
    assert r.status_code == 200


# --- routes and wiring -------------------------------------------------------


def test_inspect_route_tests_a_given_config(client, monkeypatch):
    _mock_client(monkeypatch, _site)
    r = client.post(
        "/api/stores/json-api/inspect",
        json={
            "base_url": BASE,
            "config": {**CFG, "fields": {**CFG["fields"], "price": "nope"}},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["samples"] == []
    assert body["warnings"] == ["100 of 100 items have no usable id or price."]


def test_inspect_route_422_when_nothing_found(client, monkeypatch):
    _mock_client(monkeypatch, lambda request: httpx.Response(200, text="<html/>"))
    r = client.post("/api/stores/json-api/inspect", json={"base_url": BASE})
    assert r.status_code == 422


def test_get_adapter_returns_json_api_adapter():
    assert isinstance(get_adapter(_store()), JsonApiAdapter)


def test_create_json_api_store_defaults_to_whole_catalog(client):
    r = client.post("/api/stores/", json={"type": "json_api", "base_url": BASE})
    assert r.status_code == 200
    assert [u["collection_path"] for u in r.json()["urls"]] == ["/"]
