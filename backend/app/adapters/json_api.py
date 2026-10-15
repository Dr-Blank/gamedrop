"""Adapter for a storefront that reads its catalog from a JSON API.
Nothing about the API is assumed; the store's `json_api` config maps it all."""

import asyncio
import json
import re
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from .base import StoreAdapter, store_cfg
from .woocommerce import USER_AGENT

#: Safety stop for a paging setup the server doesn't honour.
MAX_PAGES = 200

FIELDS = (
    "id",
    "title",
    "price",
    "sale_price",
    "compare_at",
    "available",
    "preorder",
    "image",
    "handle",
    "url",
)

DEFAULT_CONFIG = {
    "endpoint": "",
    "items_path": "",
    "total_path": "",
    # "offset" | "page" | "none"
    "paging": "none",
    "page_param": "",
    "size_param": "",
    "page_size": 100,
    "first_page": 1,
    "collection_param": "",
    "price_divisor": 1,
    "fields": dict.fromkeys(FIELDS, ""),
}

_TRUE_WORDS = {"true", "yes", "1", "instock", "in_stock", "in stock", "available"}
_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def normalize_config(raw: dict | None) -> dict:
    """A config with every key present, unknown keys dropped."""
    raw = raw if isinstance(raw, dict) else {}
    cfg = {k: raw.get(k, v) for k, v in DEFAULT_CONFIG.items() if k != "fields"}
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
    cfg["fields"] = {name: str(fields.get(name) or "").strip() for name in FIELDS}
    return cfg


def config_of(store) -> dict:
    try:
        return normalize_config(json.loads(store.scrape_config).get("json_api"))
    except Exception:
        return normalize_config(None)


def get_path(obj, path: str):
    """Walk a dotted path through dicts and lists; `images.0.url`. Blank is the root."""
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.lstrip("-").isdigit():
            idx = int(part)
            obj = obj[idx] if -len(obj) <= idx < len(obj) else None
        else:
            return None
        if obj is None:
            return None
    return obj


def to_num(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = _NUM_RE.search(value)
        return float(match.group().replace(",", "")) if match else None
    return None


def truthy(value) -> bool:
    """Stock-ish value as a yes/no: counts above zero, and the usual words."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE_WORDS:
            return True
        num = to_num(v)
        return num is not None and num > 0
    return False


def image_of(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("src") or value.get("href")
    return value if isinstance(value, str) and value else None


def _absolute(base_url: str, ref: str | None) -> str | None:
    """`ref` resolved against the shop; None unless it lands on http(s)."""
    if not ref:
        return None
    url = urljoin(f"{base_url}/", ref)
    return url if urlsplit(url).scheme in ("http", "https") else None


def _render(template: str, item: dict) -> str | None:
    missing = False

    def sub(m):
        nonlocal missing
        value = get_path(item, m.group(1).strip())
        if value is None or value == "":
            missing = True
            return ""
        return str(value)

    out = _TEMPLATE_RE.sub(sub, template)
    return None if missing else out


def map_item(item: dict, cfg: dict, base_url: str) -> dict | None:
    """One API item to the sync dict shape. None if it lacks an id or price."""
    if not isinstance(item, dict):
        return None
    f = cfg["fields"]

    def pick(name):
        return get_path(item, f[name]) if f[name] else None

    divisor = to_num(cfg.get("price_divisor")) or 1
    raw_price = to_num(pick("price"))
    if raw_price is None:
        return None
    price = round(raw_price / divisor, 2)
    compare_raw = to_num(pick("compare_at"))
    compare_at = round(compare_raw / divisor, 2) if compare_raw is not None else None
    sale_raw = to_num(pick("sale_price"))
    if sale_raw is not None and 0 < sale_raw / divisor < price:
        price, compare_at = round(sale_raw / divisor, 2), price
    if compare_at is not None and compare_at <= price:
        compare_at = None

    external_id = pick("id")
    if external_id is None or external_id == "":
        return None
    external_id = str(external_id)

    preorder = truthy(pick("preorder")) if f["preorder"] else False
    # An unmapped stock field means the API only lists what's for sale.
    in_stock = truthy(pick("available")) if f["available"] else True
    available = in_stock or preorder

    handle = pick("handle")
    handle = str(handle) if handle not in (None, "") else None

    url = None
    if "{" in f["url"]:
        url = _render(f["url"], item)
    elif f["url"]:
        value = pick("url")
        url = value if isinstance(value, str) and value else None
    url = _absolute(base_url, url)

    image = _absolute(base_url, image_of(pick("image")))

    return {
        "external_id": external_id,
        "title": str(pick("title") or "").strip(),
        "handle": handle,
        "url": url,
        "image_url": image,
        "variants": [
            {
                "variant_id": external_id,
                "variant_title": "Default",
                "price": price,
                "compare_at_price": compare_at,
                "available": available,
                "preorder": preorder and available,
            }
        ],
    }


def endpoint_url(cfg: dict, base_url: str) -> str:
    return urljoin(f"{base_url}/", cfg["endpoint"])


def collection_params(cfg: dict, collection_path: str) -> dict:
    """Query params a listing path adds to the API call.
    Only a path two or more segments deep names a collection; `/shop` is everything."""
    parts = urlsplit(collection_path or "/")
    params = dict(parse_qsl(parts.query))
    segments = [s for s in parts.path.split("/") if s]
    if cfg["collection_param"] and len(segments) >= 2:
        params.setdefault(cfg["collection_param"], segments[-1])
    return params


def page_params(cfg: dict, index: int, offset: int) -> dict:
    """Paging params for the `index`th request, `offset` items in."""
    style = cfg["paging"]
    params = {}
    if style in ("offset", "page") and cfg["size_param"]:
        params[cfg["size_param"]] = cfg["page_size"]
    if style == "offset" and cfg["page_param"]:
        params[cfg["page_param"]] = offset
    elif style == "page" and cfg["page_param"]:
        params[cfg["page_param"]] = int(cfg["first_page"]) + index
    return params


def items_of(body, cfg: dict) -> list:
    items = get_path(body, cfg["items_path"])
    if not isinstance(items, list):
        raise ValueError(f"no item list at '{cfg['items_path'] or '(root)'}'")
    return items


def total_of(body, cfg: dict) -> int | None:
    if not cfg["total_path"]:
        return None
    total = to_num(get_path(body, cfg["total_path"]))
    return int(total) if total is not None else None


async def fetch_page(
    client: httpx.AsyncClient, url: str, params: dict
) -> tuple[object, str]:
    r = await client.get(url, params=params or None)
    r.raise_for_status()
    return r.json(), str(r.url)


async def fetch_all(
    client: httpx.AsyncClient,
    cfg: dict,
    base_url: str,
    collection_path: str = "/",
    delay: float = 0,
    max_pages: int = MAX_PAGES,
) -> tuple[list, int | None]:
    """Every raw item the listing pages through, and the API's total if it gives one."""
    url = endpoint_url(cfg, base_url)
    fixed = collection_params(cfg, collection_path)
    raw: list = []
    seen: set[str] = set()
    total = None
    fetched = 0
    first_len = None

    for index in range(max_pages):
        if index and delay:
            await asyncio.sleep(delay)
        body, _ = await fetch_page(
            client, url, {**fixed, **page_params(cfg, index, fetched)}
        )
        items = items_of(body, cfg)
        fetched += len(items)
        total = total_of(body, cfg) if total is None else total
        fresh = []
        for item in items:
            ident = get_path(item, cfg["fields"]["id"]) if cfg["fields"]["id"] else None
            key = json.dumps(item if ident is None else ident, default=str)
            if key not in seen:
                seen.add(key)
                fresh.append(item)
        raw.extend(fresh)

        if cfg["paging"] not in ("offset", "page") or not fresh:
            break
        first_len = first_len or len(items)
        if total is not None and fetched >= total:
            break
        if total is None and len(items) < first_len:
            break
    return raw, total


class JsonApiAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        cfg = config_of(self.store)
        if not cfg["endpoint"]:
            raise ValueError("JSON API store has no endpoint configured")
        base = self.store.base_url.rstrip("/")
        async with httpx.AsyncClient(
            timeout=store_cfg(self.store, "timeout_sec"),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            raw, _ = await fetch_all(
                client,
                cfg,
                base,
                self.collection_path,
                delay=store_cfg(self.store, "request_delay_sec"),
            )
        results: dict[str, dict] = {}
        for item in raw:
            mapped = map_item(item, cfg, base)
            if mapped:
                results.setdefault(mapped["external_id"], mapped)
        return list(results.values())
