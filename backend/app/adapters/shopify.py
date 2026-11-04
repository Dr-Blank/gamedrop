import asyncio

import httpx

from ..config import get_setting
from ..logger import get_logger
from .base import StoreAdapter, store_cfg
from .throttle import RequestGate, retry_after

log = get_logger(__name__)

HEADERS = {"User-Agent": "board-game-tracker/1.0"}
RETRIES = 5
BACKOFF_SEC = 30
REQUEST_GAP_KEY = "shopify_request_gap_sec"
DEFAULT_REQUEST_GAP_SEC = 2.0
MAX_REQUEST_GAP_SEC = 60.0

# Separate shops still get 429s together, so they share one pace.
_gate = RequestGate()


def request_gap() -> float:
    """Seconds between Shopify requests; an unusable value means the default."""
    try:
        gap = float(get_setting(REQUEST_GAP_KEY))
    except ValueError:
        return DEFAULT_REQUEST_GAP_SEC
    return gap if 0 <= gap <= MAX_REQUEST_GAP_SEC else DEFAULT_REQUEST_GAP_SEC


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET through the shared gate; a 429 pauses every shop, then retries."""
    for attempt in range(RETRIES + 1):
        await _gate.wait(request_gap())
        r = await client.get(url, headers=HEADERS)
        if r.status_code != 429:
            break
        asked = retry_after(r)
        wait = BACKOFF_SEC * 2**attempt if asked is None else asked
        log.warning("shopify 429, pausing all shops for %ss: %s", wait, url)
        _gate.pause(wait)
    r.raise_for_status()
    return r


class ShopifyAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        results = []
        page = 1
        base = self.store.base_url.rstrip("/")
        collection = self.collection_path.rstrip("/")
        timeout = store_cfg(self.store, "timeout_sec")
        delay = store_cfg(self.store, "request_delay_sec")

        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                url = f"{base}{collection}/products.json?limit=250&page={page}"
                r = await _get(client, url)
                products = r.json().get("products", [])
                if not products:
                    break
                for p in products:
                    images = p.get("images", [])
                    image_url = images[0]["src"] if images else None
                    results.append(
                        {
                            "external_id": str(p["id"]),
                            "title": p["title"],
                            "handle": p.get("handle"),
                            "url": (
                                f"{base}/products/{p['handle']}"
                                if p.get("handle")
                                else None
                            ),
                            "image_url": image_url,
                            "variants": [
                                {
                                    "variant_id": str(v["id"]),
                                    "variant_title": v.get("title", "Default"),
                                    "price": float(v.get("price", 0)),
                                    "compare_at_price": (
                                        float(v["compare_at_price"])
                                        if v.get("compare_at_price")
                                        else None
                                    ),
                                    "available": v.get("available", True),
                                }
                                for v in p.get("variants", [])
                            ],
                        }
                    )
                page += 1
                if delay:
                    await asyncio.sleep(delay)

        return results

    async def fetch_product_image(self, product) -> str | None:
        """Fetch a single product's first image via Shopify's per-product JSON."""
        if not product.handle:
            return None
        base = self.store.base_url.rstrip("/")
        timeout = store_cfg(self.store, "timeout_sec")
        url = f"{base}/products/{product.handle}.json"
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await _get(client, url)
            data = r.json().get("product", {})
        images = data.get("images", [])
        return images[0]["src"] if images else None
