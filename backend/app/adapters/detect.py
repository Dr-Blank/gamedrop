"""Platform detection for the add-store form."""

from __future__ import annotations

import asyncio
import html

import httpx

from .woocommerce import API as WOO_API
from .woocommerce import USER_AGENT

TIMEOUT = 12.0


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


async def detect_platform(base_url: str) -> dict:
    """Probe a shop URL for a readable catalog. `type` is None when unknown."""
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        shopify, woo = await asyncio.gather(
            _probe_shopify(client, base),
            _probe_woocommerce(client, base),
        )

    if shopify is not None:
        return {"type": "shopify", "sample_titles": [t for t in shopify if t]}
    if woo is not None:
        return {"type": "woocommerce", "sample_titles": [t for t in woo if t]}
    return {
        "type": None,
        "sample_titles": [],
        "detail": (
            "No Shopify /products.json or WooCommerce Store API found. The shop "
            "may be on another platform, or blocking automated requests."
        ),
    }
