"""Shopify adapter: one pace across shops. HTTP is served by an httpx MockTransport."""

import asyncio
import json
from functools import partial
from types import SimpleNamespace

import httpx
import pytest

from app.adapters import shopify, throttle
from app.adapters.base import DEFAULTS
from app.adapters.shopify import ShopifyAdapter, rate_limit_retries, request_gap
from app.adapters.throttle import (
    FIRST_BLOCK_SEC,
    MAX_WAIT_SEC,
    RequestGate,
    ShopRateLimited,
)
from app.config import get_setting, set_setting
from app.scraper import ADAPTERS

GAP = shopify.DEFAULT_REQUEST_GAP_SEC
RETRIES = DEFAULTS["rate_limit_retries"]
PRODUCT = {
    "id": 1,
    "title": "Ark Nova",
    "handle": "ark-nova",
    "images": [{"src": "https://img/ark.png"}],
    "variants": [{"id": 9, "title": "Default", "price": "100.00"}],
}


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> SimpleNamespace:
    """A fresh gate on a fake clock that only sleeping moves."""
    state = SimpleNamespace(now=1000.0)
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        state.now += seconds
        await real_sleep(0)

    monkeypatch.setattr(throttle.time, "monotonic", lambda: state.now)
    monkeypatch.setattr(throttle.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(shopify, "_gate", RequestGate())
    return state


def _store(name: str = "a", **config) -> SimpleNamespace:
    return SimpleNamespace(
        base_url=f"https://{name}.test",
        scrape_config=json.dumps({"timeout_sec": 5, "request_delay_sec": 0, **config}),
    )


def _serve(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        shopify.httpx,
        "AsyncClient",
        partial(httpx.AsyncClient, transport=httpx.MockTransport(handler)),
    )


def _one_page(request: httpx.Request) -> httpx.Response:
    page_one = request.url.params.get("page") == "1"
    return httpx.Response(200, json={"products": [PRODUCT] if page_one else []})


def _fetch(*stores):
    async def run():
        return await asyncio.gather(
            *(ShopifyAdapter(s, "/collections/all").fetch_products() for s in stores)
        )

    return asyncio.run(run())


def test_fetch_products_walks_pages_and_maps_them(monkeypatch):
    _serve(monkeypatch, _one_page)
    [products] = _fetch(_store())
    assert products[0]["external_id"] == "1"
    assert products[0]["url"] == "https://a.test/products/ark-nova"
    assert products[0]["variants"][0]["price"] == 100.0


def test_shops_share_one_pace(monkeypatch, clock):
    times = []

    def handler(request):
        times.append(clock.now)
        return _one_page(request)

    _serve(monkeypatch, handler)
    _fetch(_store("a"), _store("b"))
    assert len(times) == 4
    assert [b - a for a, b in zip(times, times[1:], strict=False)] == [GAP] * 3


def test_429_waits_retry_after_then_retries(monkeypatch, clock):
    calls = []

    def handler(request):
        calls.append((request.url.host, clock.now))
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7.5"})
        return _one_page(request)

    _serve(monkeypatch, handler)
    a, b = _fetch(_store("a"), _store("b"))
    assert a and b
    refused_at = calls[0][1]
    retried_at = next(at for host, at in calls[1:] if host == "a.test")
    assert retried_at >= refused_at + 7.5
    assert sum(host == "a.test" for host, _ in calls) == 3


def test_a_pause_holds_back_only_that_shop(clock):
    gate = RequestGate()
    gate.pause("a", 100)
    asyncio.run(gate.wait("b", 0))
    assert clock.now == 1000.0
    asyncio.run(gate.wait("a", 0))
    assert clock.now == 1100.0


def test_retry_after_zero_is_taken_at_its_word(monkeypatch, clock):
    answers = [httpx.Response(429, headers={"Retry-After": "0"})]
    _serve(
        monkeypatch,
        lambda request: answers.pop() if answers else _one_page(request),
    )
    _fetch(_store())
    assert clock.now == 1000.0 + 2 * GAP


def test_429_without_retry_after_backs_off_harder_each_time(monkeypatch, clock):
    refusals = 2
    times = []

    def handler(request):
        times.append(clock.now)
        if len(times) <= refusals:
            return httpx.Response(429)
        return _one_page(request)

    _serve(monkeypatch, handler)
    _fetch(_store())
    assert times[1] - times[0] == shopify.BACKOFF_SEC
    assert times[2] - times[1] == shopify.BACKOFF_SEC * 2


def test_gives_up_after_the_last_retry_with_the_429(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"})

    _serve(monkeypatch, handler)
    with pytest.raises(ShopRateLimited, match="rate limited by shop"):
        _fetch(_store())
    assert len(calls) == RETRIES + 1


@pytest.mark.parametrize("retries", [0, 5])
def test_retries_are_set_per_shop(monkeypatch, retries):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"})

    _serve(monkeypatch, handler)
    with pytest.raises(ShopRateLimited):
        _fetch(_store(rate_limit_retries=retries))
    assert len(calls) == retries + 1


@pytest.mark.parametrize("bad", ["soon", -1, 11, None, float("inf")])
def test_unusable_retries_mean_the_default(bad):
    assert rate_limit_retries(_store(rate_limit_retries=bad)) == RETRIES


def test_backoff_without_retry_after_is_capped(monkeypatch, clock):
    times = []

    def handler(request):
        times.append(clock.now)
        return httpx.Response(429)

    _serve(monkeypatch, handler)
    with pytest.raises(ShopRateLimited):
        _fetch(_store(rate_limit_retries=10))
    assert max(b - a for a, b in zip(times, times[1:], strict=False)) == MAX_WAIT_SEC


def test_a_blocked_shop_gets_no_requests_until_the_block_ends(monkeypatch, clock):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "a.test":
            return httpx.Response(429, headers={"Retry-After": "1"})
        return _one_page(request)

    _serve(monkeypatch, handler)
    with pytest.raises(ShopRateLimited):
        _fetch(_store("a"))
    calls.clear()

    with pytest.raises(ShopRateLimited, match="next try in 1h"):
        _fetch(_store("a"))
    assert calls == []

    assert _fetch(_store("b"))[0]

    clock.now += FIRST_BLOCK_SEC
    calls.clear()
    with pytest.raises(ShopRateLimited, match="next try in 2h"):
        _fetch(_store("a"))
    assert calls == ["a.test"] * (RETRIES + 1)


def test_blocks_grow_up_to_a_cap_and_success_resets_them():
    gate = RequestGate()
    messages = [str(gate.block("a")) for _ in range(6)]
    assert [m.rsplit(" ", 1)[1] for m in messages] == [
        "1h",
        "2h",
        "4h",
        "8h",
        "12h",
        "12h",
    ]
    gate.clear("a")
    assert str(gate.block("a")).endswith("1h")
    asyncio.run(gate.wait("b", 0))


def test_other_errors_are_not_retried(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    _serve(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError, match="500"):
        _fetch(_store())
    assert len(calls) == 1


def test_image_fetch_shares_the_gate_and_retries(monkeypatch, clock):
    times = []

    def handler(request):
        times.append(clock.now)
        if len(times) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"product": PRODUCT})

    _serve(monkeypatch, handler)
    product = SimpleNamespace(handle="ark-nova")
    url = asyncio.run(ShopifyAdapter(_store()).fetch_product_image(product))
    assert url == "https://img/ark.png"
    assert times[1] - times[0] == 3


def test_a_pause_landing_mid_wait_extends_it(clock):
    gate = RequestGate()

    async def run():
        await gate.wait("a", GAP)
        waiting = asyncio.create_task(gate.wait("a", GAP))
        await asyncio.sleep(0)
        gate.pause("a", 10)
        await waiting

    asyncio.run(run())
    assert clock.now >= 1000.0 + 10


def test_request_gap_defaults_and_reads_the_setting():
    assert request_gap() == GAP
    set_setting(shopify.REQUEST_GAP_KEY, "5")
    assert request_gap() == 5


@pytest.mark.parametrize("bad", ["soon", "-1", "nan", "inf", "61"])
def test_request_gap_ignores_unusable_values(bad):
    set_setting(shopify.REQUEST_GAP_KEY, bad)
    assert request_gap() == GAP


def test_request_gap_of_zero_means_no_gap():
    set_setting(shopify.REQUEST_GAP_KEY, "0")
    assert request_gap() == 0


def test_no_warning_until_a_shop_answers_429(monkeypatch):
    _serve(monkeypatch, _one_page)
    _fetch(_store())
    assert ShopifyAdapter.warning() is None


def test_first_429_from_any_shop_raises_the_warning_and_keeps_its_date(monkeypatch):
    answers = [httpx.Response(429, headers={"Retry-After": "0"})]
    _serve(
        monkeypatch,
        lambda request: answers.pop() if answers else _one_page(request),
    )
    _fetch(_store("a"))

    warning = ShopifyAdapter.warning()
    first = warning["since"]
    assert first == get_setting(shopify.FIRST_429_KEY)
    assert any("24h" in tip for tip in warning["tips"])
    assert any("retries" in tip for tip in warning["tips"])

    answers.append(httpx.Response(429, headers={"Retry-After": "0"}))
    set_setting(shopify.FIRST_429_KEY, "2020-01-01T00:00:00")
    _fetch(_store("b"))
    assert ShopifyAdapter.warning()["since"] == "2020-01-01T00:00:00"


def test_only_shopify_has_a_warning(monkeypatch):
    set_setting(shopify.FIRST_429_KEY, "2020-01-01T00:00:00")
    assert ShopifyAdapter.warning()
    others = [a for name, a in ADAPTERS.items() if name != "shopify"]
    assert others and all(a.warning() is None for a in others)
