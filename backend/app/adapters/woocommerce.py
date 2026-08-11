"""WooCommerce adapter, reading the public Store API (`/wp-json/wc/store/v1`).

Chosen over the authenticated `wc/v3` REST API because the Store API needs no
API keys — same trade as Shopify's `products.json`.
"""

import asyncio
import html

import httpx

from .base import StoreAdapter, store_cfg

API = "/wp-json/wc/store/v1"
PER_PAGE = 100
USER_AGENT = "board-game-tracker/1.0"


def _to_major(prices: dict, key: str) -> float | None:
    """Store API prices are minor-unit integers: "425000" at unit 2 is 4250.00."""
    raw = prices.get(key)
    if raw is None or raw == "":
        return None
    try:
        minor = int(prices.get("currency_minor_unit") or 0)
        return round(float(raw) / (10**minor), 2)
    except (TypeError, ValueError):
        return None


def category_slug(collection_path: str | None) -> str | None:
    """Last slug of a category path; None means the whole catalog."""
    segments = [s for s in (collection_path or "").split("/") if s]
    if segments and segments[0] == "product-category":
        segments = segments[1:]
    return segments[-1] if segments else None


def _price_fields(product: dict) -> tuple[float | None, float | None]:
    prices = product.get("prices") or {}
    price_range = prices.get("price_range")
    if price_range:
        # Variable products advertise their low end ("from ₹999").
        price = _to_major(prices, "price") or _to_major(
            {**prices, **price_range}, "min_amount"
        )
    else:
        price = _to_major(prices, "price")
    regular = _to_major(prices, "regular_price")
    compare_at = (
        regular if (price is not None and regular and regular > price) else None
    )
    return price, compare_at


def map_product(product: dict) -> dict | None:
    """Store API product to the sync dict shape. None if it has no usable price."""
    price, compare_at = _price_fields(product)
    if price is None:
        return None

    images = product.get("images") or []
    external_id = str(product["id"])

    return {
        "external_id": external_id,
        "title": html.unescape(product.get("name") or "").strip(),
        "handle": product.get("slug"),
        "url": product.get("permalink"),
        "image_url": images[0].get("src") if images else None,
        "variants": [
            {
                # Listings don't price variations individually, so one line per
                # product; keying on the product id keeps history stable.
                "variant_id": external_id,
                "variant_title": "Default",
                "price": price,
                "compare_at_price": compare_at,
                "available": bool(product.get("is_in_stock"))
                and not product.get("is_on_backorder"),
            }
        ],
    }


class WooCommerceAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        base = self.store.base_url.rstrip("/")
        timeout = store_cfg(self.store, "timeout_sec")
        delay = store_cfg(self.store, "request_delay_sec")

        results: list[dict] = []
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        ) as client:
            category_id = await self._resolve_category(client, base)

            page = 1
            while True:
                params = {
                    "per_page": PER_PAGE,
                    "page": page,
                    # Default ordering reshuffles rows between page fetches.
                    "orderby": "id",
                    "order": "asc",
                }
                if category_id is not None:
                    params["category"] = category_id
                r = await client.get(f"{base}{API}/products", params=params)
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                for raw in batch:
                    mapped = map_product(raw)
                    if mapped:
                        results.append(mapped)
                total_pages = int(r.headers.get("x-wp-totalpages") or 0)
                if len(batch) < PER_PAGE or (total_pages and page >= total_pages):
                    break
                page += 1
                if delay:
                    await asyncio.sleep(delay)

        return results

    async def fetch_product_image(self, product) -> str | None:
        if not product.external_id:
            return None
        base = self.store.base_url.rstrip("/")
        timeout = store_cfg(self.store, "timeout_sec")
        async with httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}
        ) as client:
            r = await client.get(f"{base}{API}/products/{product.external_id}")
            r.raise_for_status()
            images = r.json().get("images") or []
        return images[0].get("src") if images else None

    async def _resolve_category(
        self, client: httpx.AsyncClient, base: str
    ) -> int | None:
        """Category slug to term id, since the products route filters by id."""
        slug = category_slug(self.store.collection_path)
        if not slug:
            return None

        page = 1
        while True:
            r = await client.get(
                f"{base}{API}/products/categories",
                params={"per_page": PER_PAGE, "page": page},
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for category in batch:
                if category.get("slug") == slug:
                    return int(category["id"])
            if len(batch) < PER_PAGE:
                break
            page += 1

        raise ValueError(f"category not found on store: {slug}")
