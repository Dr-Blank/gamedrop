"""Wix Stores adapter, reading the product gallery a shop page server-renders.

Wix has no keyless catalog API, but gallery pages embed their products as JSON
and `?page=N` renders the first N pages at once — two requests read a gallery.
"""

import asyncio
import json
import math
import re

import httpx

from .base import StoreAdapter, store_cfg
from .woocommerce import USER_AGENT

_WARMUP_RE = re.compile(
    r'<script[^>]*id="wix-warmup-data"[^>]*>(.*?)</script>', re.DOTALL
)


def _num(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def find_gallery(page_html: str) -> dict | None:
    """The `productsWithMetaData` block of a page's product gallery, if any."""
    match = _WARMUP_RE.search(page_html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    for app in (data.get("appsWarmupData") or {}).values():
        if not isinstance(app, dict):
            continue
        for widget in app.values():
            catalog = widget.get("catalog") if isinstance(widget, dict) else None
            products = ((catalog or {}).get("category") or {}).get(
                "productsWithMetaData"
            )
            if isinstance(products, dict) and isinstance(products.get("list"), list):
                return products
    return None


def map_product(product: dict, base_url: str) -> dict | None:
    """Gallery product to the sync dict shape. None if it has no usable price."""
    price = _num(product.get("price"))
    if price is None:
        return None
    # Wix names these inversely: `comparePrice` is the discounted price.
    sale = _num(product.get("comparePrice"))
    if sale and sale < price:
        price, compare_at = sale, price
    else:
        compare_at = None

    media = product.get("media") or []
    slug = product.get("urlPart")
    external_id = str(product["id"])

    return {
        "external_id": external_id,
        "title": (product.get("name") or "").strip(),
        "handle": slug,
        "url": f"{base_url}/product-page/{slug}" if slug else None,
        "image_url": media[0].get("fullUrl") if media else None,
        "variants": [
            {
                # Galleries don't price option choices, so one line per product.
                "variant_id": external_id,
                "variant_title": "Default",
                "price": price,
                "compare_at_price": compare_at,
                "available": bool(product.get("isInStock")),
            }
        ],
    }


class WixAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        base = self.store.base_url.rstrip("/")
        url = f"{base}{self.collection_path.rstrip('/')}"
        timeout = store_cfg(self.store, "timeout_sec")
        delay = store_cfg(self.store, "request_delay_sec")

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            gallery = await self._gallery(client, url, None)
            rendered = gallery["list"]
            total = int(gallery.get("totalCount") or 0)
            if rendered and len(rendered) < total:
                if delay:
                    await asyncio.sleep(delay)
                pages = math.ceil(total / len(rendered))
                rendered = (await self._gallery(client, url, pages))["list"]

        results: dict[str, dict] = {}
        for raw in rendered:
            mapped = map_product(raw, base)
            if mapped:
                results.setdefault(mapped["external_id"], mapped)
        return list(results.values())

    async def _gallery(
        self, client: httpx.AsyncClient, url: str, pages: int | None
    ) -> dict:
        r = await client.get(url, params={"page": pages} if pages else None)
        r.raise_for_status()
        gallery = find_gallery(r.text)
        if gallery is None:
            raise ValueError(f"no product gallery on page: {self.collection_path}")
        return gallery
