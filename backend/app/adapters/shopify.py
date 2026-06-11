import asyncio
import json

import httpx

from .base import StoreAdapter

_DEFAULTS = {"timeout_sec": 30, "request_delay_sec": 1, "sync_interval_hours": 6}


def _cfg(store, key):
    try:
        return json.loads(store.scrape_config).get(key, _DEFAULTS[key])
    except Exception:
        return _DEFAULTS[key]


class ShopifyAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        results = []
        page = 1
        base = self.store.base_url.rstrip("/")
        collection = self.store.collection_path.rstrip("/")
        timeout = _cfg(self.store, "timeout_sec")
        delay = _cfg(self.store, "request_delay_sec")

        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                url = f"{base}{collection}/products.json?limit=250&page={page}"
                r = await client.get(
                    url, headers={"User-Agent": "board-game-tracker/1.0"}
                )
                r.raise_for_status()
                products = r.json().get("products", [])
                if not products:
                    break
                for p in products:
                    results.append({
                        "external_id": str(p["id"]),
                        "title": p["title"],
                        "handle": p.get("handle"),
                        "url": (
                            f"{base}/products/{p['handle']}"
                            if p.get("handle") else None
                        ),
                        "variants": [
                            {
                                "variant_id": str(v["id"]),
                                "variant_title": v.get("title", "Default"),
                                "price": float(v.get("price", 0)),
                                "compare_at_price": (
                                    float(v["compare_at_price"])
                                    if v.get("compare_at_price") else None
                                ),
                                "available": v.get("available", True),
                            }
                            for v in p.get("variants", [])
                        ],
                    })
                page += 1
                if delay:
                    await asyncio.sleep(delay)

        return results
