"""OpenCart listing adapter. HTTP is served by an httpx MockTransport."""

import asyncio
from functools import partial

import httpx
import pytest

from app.adapters import detect, opencart
from app.adapters.detect import detect_platform
from app.adapters.opencart import (
    BACKOFF_SEC,
    PAGE_LIMIT,
    RETRIES,
    THROTTLED_DELAY_SEC,
    OpenCartAdapter,
    has_next_page,
    map_card,
    parse_cards,
    parse_price,
)
from app.models import Store
from app.scraper import get_adapter

BASE = "https://shop.test"


def _card(
    pid: int = 42,
    name: str = "Catan &amp; Friends",
    slug: str = "catan",
    price: str = "₹ 3,499.00",
    old: str | None = None,
    out_of_stock: bool = False,
) -> str:
    """A product card as the Journal3 theme renders it."""
    classes = "product-layout" + (" out-of-stock" if out_of_stock else "")
    if old:
        prices = f'<span class="price-new">{price}</span> <span class="price-old">{old}</span>'
    else:
        prices = f'<span class="price-normal">{price}</span>'
    return f"""
  <div class="{classes} has-extra-button " data-product-id="{pid}">
    <div class="product-thumb">
      <a href="{BASE}/{slug}" class="product-img" title="x">
        <img src="{BASE}/image/cache/{slug}-375x375.webp" class="img-responsive"/>
      </a>
      <div class="caption">
        <div class="name"><a href="{BASE}/{slug}" title="x">{name}</a></div>
        <div class="price"><div>{prices}</div>
          <span class="price-tax">Ex Tax:{price}</span>
        </div>
        <a class="btn btn-cart" onclick="cart.add('{pid}', 1);">Add to Cart</a>
      </div>
    </div>
  </div>"""


def _pager(page: int, last: int) -> str:
    links = "".join(
        f'<li><a href="{BASE}/board-games?limit=100&amp;page={n}">{n}</a></li>'
        for n in range(1, last + 1)
        if n != page
    )
    return f'<ul class="pagination"><li class="active">{page}</li>{links}</ul>'


def _page(cards: list[str], page: int = 1, last: int = 1) -> str:
    return (
        '<html><head><link href="catalog/view/theme/journal3/style.css"></head>'
        '<body><div class="main-products product-grid">'
        f"{''.join(cards)}</div>{_pager(page, last)}</body></html>"
    )


def _catalog(n: int) -> list[str]:
    return [_card(pid=i, name=f"Game {i}", slug=f"game-{i}") for i in range(1, n + 1)]


def _store(**overrides) -> Store:
    store = Store(
        id="ocshop",
        name="OC Shop",
        type="opencart",
        base_url=BASE,
        scrape_config='{"timeout_sec":5,"request_delay_sec":0}',
    )
    for key, value in overrides.items():
        setattr(store, key, value)
    return store


def _adapter(collection_path: str = "/board-games") -> OpenCartAdapter:
    return OpenCartAdapter(_store(), collection_path)


def _mock_client(monkeypatch, module, handler):
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record backoff and pacing sleeps instead of waiting them out."""
    waited: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(opencart.asyncio, "sleep", fake_sleep)
    return waited


def _listing_handler(catalog: list[str], calls: list | None = None):
    """Serve `catalog` paged by the request's `limit` and `page`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url)
        limit = int(request.url.params.get("limit", 20))
        page = int(request.url.params.get("page", 1))
        last = -(-len(catalog) // limit)
        rows = catalog[(page - 1) * limit : page * limit]
        return httpx.Response(200, text=_page(rows, page, last))

    return handler


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("₹ 1,300.00", 1300.0),
        ("$122.00", 122.0),
        ("1.299,50 €", 1299.5),
        ("13,50 €", 13.5),
        ("Rs. 12,999", 12999.0),
        ("1.234.567", 1234567.0),
        ("Call for price", None),
        (None, None),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    ("page", "last", "expected"),
    [(1, 3, True), (2, 3, True), (3, 3, False), (1, 1, False)],
)
def test_has_next_page_reads_pager_links(page, last, expected):
    assert has_next_page(_page([], page, last), page) is expected


def test_has_next_page_false_without_pager():
    assert has_next_page("<html></html>", 1) is False


def test_parse_cards_stays_inside_main_grid():
    html = (
        _card(pid=1)
        + '<div class="main-products">'
        + _card(pid=2)
        + '</div><ul class="pagination"></ul>'
        + _card(pid=3)
    )
    cards = parse_cards(html)
    assert [map_card(c)["external_id"] for c in cards] == ["2"]


def test_parse_cards_reads_whole_page_without_grid_marker():
    assert len(parse_cards(_card(pid=1) + _card(pid=2))) == 2


def test_map_card_regular_price():
    mapped = map_card(parse_cards(_page([_card()]))[0])
    assert mapped["external_id"] == "42"
    assert mapped["title"] == "Catan & Friends"
    assert mapped["handle"] == "catan"
    assert mapped["url"] == f"{BASE}/catan"
    assert mapped["image_url"] == f"{BASE}/image/cache/catan-375x375.webp"
    variant = mapped["variants"][0]
    assert variant["price"] == 3499.0
    assert variant["compare_at_price"] is None
    assert variant["available"] is True


def test_map_card_special_price():
    card = _card(price="₹ 1,300.00", old="₹ 1,399.00")
    variant = map_card(parse_cards(card)[0])["variants"][0]
    assert variant["price"] == 1300.0
    assert variant["compare_at_price"] == 1399.0


def test_map_card_out_of_stock():
    variant = map_card(parse_cards(_card(out_of_stock=True))[0])["variants"][0]
    assert variant["available"] is False


def test_map_card_skips_priceless_cards():
    assert map_card(parse_cards(_card(price="Call for price"))[0]) is None


def test_map_card_reads_default_theme_markup():
    card = """
    <div class="product-layout col-lg-3">
      <div class="product-thumb">
        <div class="image"><a href="https://s.test/index.php?route=product/product&amp;product_id=7">
          <img src="https://s.test/image/7.jpg" /></a></div>
        <div class="caption">
          <h4><a href="https://s.test/index.php?route=product/product&amp;product_id=7">Azul</a></h4>
          <p class="price">
            $45.00 <span class="price-tax">Ex Tax: $40.00</span>
          </p>
        </div>
        <button type="button" onclick="cart.add('7', '1');">Add</button>
      </div>
    </div>"""
    mapped = map_card(parse_cards(card)[0])
    assert mapped["external_id"] == "7"
    assert mapped["title"] == "Azul"
    assert (
        mapped["url"] == "https://s.test/index.php?route=product/product&product_id=7"
    )
    assert mapped["handle"] is None
    assert mapped["variants"][0]["price"] == 45.0


# --- fetch_products ----------------------------------------------------------


def test_fetch_products_short_page_makes_one_request(monkeypatch):
    calls: list = []
    _mock_client(monkeypatch, opencart, _listing_handler(_catalog(5), calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 5
    assert len(calls) == 1
    assert calls[0].path == "/board-games"
    assert calls[0].params["limit"] == str(PAGE_LIMIT)


def test_fetch_products_walks_pages(monkeypatch):
    calls: list = []
    catalog = _catalog(PAGE_LIMIT + 30)
    _mock_client(monkeypatch, opencart, _listing_handler(catalog, calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == PAGE_LIMIT + 30
    assert [c.params["page"] for c in calls] == ["1", "2"]


def test_fetch_products_continues_past_short_mid_catalog_page(monkeypatch):
    calls: list = []
    catalog = _catalog(250)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        page = int(request.url.params["page"])
        rows = catalog[(page - 1) * PAGE_LIMIT : page * PAGE_LIMIT]
        if page == 1:
            rows = rows[:-1]
        return httpx.Response(200, text=_page(rows, page, 3))

    _mock_client(monkeypatch, opencart, handler)

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 249
    assert [c.params["page"] for c in calls] == ["1", "2", "3"]


def test_fetch_products_stops_when_page_repeats(monkeypatch):
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, text=_page(_catalog(PAGE_LIMIT), 1, 5))

    _mock_client(monkeypatch, opencart, handler)

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == PAGE_LIMIT
    assert len(calls) == 2


def test_fetch_products_keeps_route_query(monkeypatch):
    calls: list = []
    _mock_client(monkeypatch, opencart, _listing_handler(_catalog(2), calls))

    asyncio.run(_adapter("/index.php?route=product/category&path=20").fetch_products())

    assert calls[0].params["route"] == "product/category"
    assert calls[0].params["path"] == "20"
    assert calls[0].params["limit"] == str(PAGE_LIMIT)


def test_fetch_products_raises_without_grid(monkeypatch):
    _mock_client(
        monkeypatch, opencart, lambda request: httpx.Response(200, text=_page([]))
    )
    with pytest.raises(ValueError, match="no product grid"):
        asyncio.run(_adapter("/about").fetch_products())


def test_fetch_products_raises_when_a_promised_page_is_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        rows = _catalog(PAGE_LIMIT) if page == 1 else []
        return httpx.Response(200, text=_page(rows, page, 3))

    _mock_client(monkeypatch, opencart, handler)
    with pytest.raises(ValueError, match="no product grid on page 2"):
        asyncio.run(_adapter().fetch_products())


def test_fetch_products_raises_on_http_error(monkeypatch):
    _mock_client(monkeypatch, opencart, lambda request: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_adapter().fetch_products())


# --- timeouts and blocks -----------------------------------------------------


def _flaky(failures: list, catalog: list[str], calls: list):
    """Answer each request with the next queued failure, then the listing."""
    listing = _listing_handler(catalog)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failures:
            failure = failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        return listing(request)

    return handler


@pytest.mark.parametrize("status", [403, 429, 503, 522])
def test_fetch_page_retries_refusals_with_backoff(monkeypatch, sleeps, status):
    calls: list = []
    failures = [httpx.Response(status), httpx.Response(status)]
    _mock_client(monkeypatch, opencart, _flaky(failures, _catalog(3), calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 3
    assert len(calls) == 3
    assert sleeps == [BACKOFF_SEC, BACKOFF_SEC * 2]


def test_fetch_page_honours_retry_after(monkeypatch, sleeps):
    calls: list = []
    failures = [httpx.Response(429, headers={"retry-after": "7"})]
    _mock_client(monkeypatch, opencart, _flaky(failures, _catalog(3), calls))

    asyncio.run(_adapter().fetch_products())

    assert sleeps == [7.0]


def test_fetch_page_retries_timeouts_with_longer_cutoff(monkeypatch, sleeps):
    calls: list = []
    failures = [httpx.ReadTimeout("slow"), httpx.ConnectError("reset")]
    _mock_client(monkeypatch, opencart, _flaky(failures, _catalog(3), calls))

    products = asyncio.run(_adapter().fetch_products())

    assert len(products) == 3
    assert [c.extensions["timeout"]["read"] for c in calls] == [5, 10, 15]


def test_fetch_page_retries_block_pages_without_shop_markup(monkeypatch, sleeps):
    calls: list = []
    failures = [httpx.Response(200, text="<html>Just a moment...</html>")]
    _mock_client(monkeypatch, opencart, _flaky(failures, _catalog(3), calls))

    assert len(asyncio.run(_adapter().fetch_products())) == 3
    assert len(calls) == 2


def test_fetch_page_gives_up_after_retries(monkeypatch, sleeps):
    calls: list = []
    failures = [httpx.Response(403) for _ in range(RETRIES + 1)]
    _mock_client(monkeypatch, opencart, _flaky(failures, [], calls))

    with pytest.raises(RuntimeError, match="HTTP 403"):
        asyncio.run(_adapter().fetch_products())
    assert len(calls) == RETRIES + 1
    assert len(sleeps) == RETRIES


def test_refusal_slows_the_rest_of_the_walk(monkeypatch, sleeps):
    calls: list = []
    failures = [httpx.Response(429, headers={"retry-after": "1"})]
    catalog = _catalog(PAGE_LIMIT * 2 + 1)
    _mock_client(monkeypatch, opencart, _flaky(failures, catalog, calls))

    asyncio.run(_adapter().fetch_products())

    # Configured delay is 0; one refusal raises the page gap from then on.
    assert sleeps == [1.0, THROTTLED_DELAY_SEC, THROTTLED_DELAY_SEC]


# --- detection ---------------------------------------------------------------


def test_detect_platform_finds_opencart_with_samples(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=_page(_catalog(5)))
        return httpx.Response(404, text="<html>not found</html>")

    _mock_client(monkeypatch, detect, handler)

    result = asyncio.run(detect_platform(BASE))

    assert result["type"] == "opencart"
    assert result["sample_titles"] == ["Game 1", "Game 2", "Game 3"]


def test_detect_platform_opencart_by_session_cookie(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200, text="<html></html>", headers={"set-cookie": "OCSESSID=abc"}
            )
        return httpx.Response(404)

    _mock_client(monkeypatch, detect, handler)

    result = asyncio.run(detect_platform(BASE))

    assert result["type"] == "opencart"
    assert result["sample_titles"] == []


def test_detect_platform_ignores_plain_sites(monkeypatch):
    _mock_client(
        monkeypatch, detect, lambda request: httpx.Response(200, text="<html/>")
    )
    assert asyncio.run(detect_platform(BASE))["type"] is None


# --- wiring ------------------------------------------------------------------


def test_get_adapter_returns_opencart_adapter():
    assert isinstance(get_adapter(_store()), OpenCartAdapter)


def test_create_opencart_store_defaults_to_board_games_path(client):
    r = client.post(
        "/api/stores/",
        json={"type": "opencart", "base_url": "https://ocshop.test"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "opencart"
    assert [u["collection_path"] for u in body["urls"]] == ["/board-games"]
