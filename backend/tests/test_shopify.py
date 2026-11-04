"""Shopify adapter: one pace across shops. HTTP is served by an httpx MockTransport."""

import asyncio
from functools import partial
from types import SimpleNamespace

import httpx
import pytest

from app.adapters import shopify, throttle
from app.adapters.shopify import RETRIES, ShopifyAdapter, request_gap
from app.adapters.throttle import RequestGate
from app.config import set_setting

GAP = shopify.DEFAULT_REQUEST_GAP_SEC
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


def _store(name: str = "a") -> SimpleNamespace:
    return SimpleNamespace(
        base_url=f"https://{name}.test",
        scrape_config='{"timeout_sec":5,"request_delay_sec":0}',
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


def test_429_waits_retry_after_for_every_shop_then_retries(monkeypatch, clock):
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
    assert all(at >= refused_at + 7.5 for _, at in calls[1:])
    assert sum(host == "a.test" for host, _ in calls) == 3


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
    with pytest.raises(httpx.HTTPStatusError, match="429"):
        _fetch(_store())
    assert len(calls) == RETRIES + 1


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
        await gate.wait(GAP)
        waiting = asyncio.create_task(gate.wait(GAP))
        await asyncio.sleep(0)
        gate.pause(10)
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
