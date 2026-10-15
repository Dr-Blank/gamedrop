"""Platform detection for the add-store form."""

from __future__ import annotations

import asyncio
import html

import httpx

from .json_api import normalize_config
from .json_api_discover import discover, preview
from .opencart import is_opencart, map_card, parse_cards
from .wix import find_gallery
from .woocommerce import API as WOO_API
from .woocommerce import USER_AGENT

TIMEOUT = 12.0
#: Cap on hunting for a JSON API, which may probe dozens of URLs.
DISCOVERY_BUDGET = 60.0


async def _probe_shopify(client: httpx.AsyncClient, base: str) -> list[str] | None:
    try:
        r = await client.get(f"{base}/products.json", params={"limit": 3})
        r.raise_for_status()
        products = r.json().get("products")
    except Exception:
        return None
    if not isinstance(products, list):
        return None
    return [p.get("title", "") for p in products]


async def _probe_woocommerce(client: httpx.AsyncClient, base: str) -> list[str] | None:
    try:
        r = await client.get(f"{base}{WOO_API}/products", params={"per_page": 3})
        r.raise_for_status()
        products = r.json()
    except Exception:
        return None
    if not isinstance(products, list):
        return None
    return [html.unescape(p.get("name", "")) for p in products]


async def _probe_wix(client: httpx.AsyncClient, base: str) -> list[str] | None:
    """Wix answers every path with its request-id header, even a 404."""
    try:
        r = await client.get(f"{base}/shop")
    except Exception:
        return None
    if "x-wix-request-id" not in r.headers:
        return None
    gallery = find_gallery(r.text) if r.is_success else None
    return [p.get("name", "") for p in (gallery or {}).get("list", [])[:3]]


async def _probe_opencart(client: httpx.AsyncClient, base: str) -> list[str] | None:
    try:
        r = await client.get(f"{base}/")
    except Exception:
        return None
    if not r.is_success or not is_opencart(r):
        return None
    mapped = (map_card(card) for card in parse_cards(r.text))
    return [m["title"] for m in mapped if m][:3]


async def inspect_json_api(
    client: httpx.AsyncClient,
    base: str,
    api_url: str | None = None,
    config: dict | None = None,
    collection_path: str = "/",
) -> dict | None:
    """A JSON API config with a live sample: `config` as given, else discovered."""
    if config is None:
        config = await discover(client, base, api_url)
        if config is None:
            return None
    config = normalize_config(config)
    try:
        return await preview(client, config, base, collection_path)
    except Exception as e:
        return {
            "config": config,
            "total": None,
            "samples": [],
            "warnings": [f"Request failed: {e}"],
        }


async def detect_platform(base_url: str) -> dict:
    """Probe a shop URL for a readable catalog. `type` is None when unknown."""
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        shopify, woo, wix, opencart = await asyncio.gather(
            _probe_shopify(client, base),
            _probe_woocommerce(client, base),
            _probe_wix(client, base),
            _probe_opencart(client, base),
        )
        for name, titles in (
            ("shopify", shopify),
            ("woocommerce", woo),
            ("wix", wix),
            ("opencart", opencart),
        ):
            if titles is not None:
                return {"type": name, "sample_titles": [t for t in titles if t]}

        # Last, as it reads every script on the homepage.
        try:
            found = await asyncio.wait_for(
                inspect_json_api(client, base), DISCOVERY_BUDGET
            )
        except TimeoutError:
            found = None

    if found:
        return {
            "type": "json_api",
            "sample_titles": [s["title"] for s in found["samples"][:3]],
            "json_api": found,
        }
    return {
        "type": None,
        "sample_titles": [],
        "detail": (
            "No Shopify, WooCommerce, Wix or OpenCart store, and no product "
            "API in the storefront's scripts. Paste the API URL the shop page "
            "loads its products from, or the shop may be blocking automated "
            "requests."
        ),
    }
