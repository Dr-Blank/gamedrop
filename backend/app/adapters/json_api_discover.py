"""Find a storefront's product API and guess a `json_api` config for it.
Every guess comes back with sample rows for the user to confirm before saving."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .json_api import (
    DEFAULT_CONFIG,
    fetch_all,
    get_path,
    map_item,
    normalize_config,
    total_of,
)

MAX_SCRIPTS = 40
SAMPLE_SIZE = 5

COMMON_ENDPOINTS = (
    "/api/products",
    "/api/v1/products",
    "/api/v2/products",
    "/api/store/products",
    "/api/catalog/products",
    "/api/shop/products",
)

FIELD_CANDIDATES = {
    "id": ("id", "_id", "uuid", "productId", "product_id", "sku"),
    "title": ("name", "title", "productName", "product_name"),
    "price": ("price", "currentPrice", "sellingPrice", "selling_price", "finalPrice"),
    "sale_price": ("salePrice", "sale_price", "discountPrice", "specialPrice"),
    "compare_at": (
        "comparePrice",
        "compare_at_price",
        "compareAtPrice",
        "mrp",
        "MRP",
        "originalPrice",
        "original_price",
        "regularPrice",
        "regular_price",
        "listPrice",
        "list_price",
        "oldPrice",
    ),
    # Yes/no flags ahead of counts: some APIs carry both.
    "available": (
        "inStock",
        "in_stock",
        "isInStock",
        "is_in_stock",
        "available",
        "isAvailable",
        "is_available",
        "stockStatus",
        "stock_status",
        "availability",
        "stock",
        "quantity",
        "stockQuantity",
        "stock_quantity",
        "inventory",
        "inventoryQuantity",
    ),
    "preorder": (
        "isPreOrder",
        "isPreorder",
        "preOrder",
        "preorder",
        "is_preorder",
        "is_pre_order",
        "pre_order",
    ),
    "image": (
        "images",
        "image",
        "imageUrl",
        "image_url",
        "thumbnail",
        "featuredImage",
        "featured_image",
        "mainImage",
    ),
    "handle": ("slug", "handle", "urlKey", "url_key"),
    "url": ("url", "productUrl", "product_url", "permalink", "link", "href"),
}

_LIST_KEYS = ("products", "items", "data", "results", "docs", "records", "nodes")
_TOTAL_KEYS = (
    "total",
    "totalCount",
    "total_count",
    "totalItems",
    "total_items",
)
_NESTED_PRICE = ("amount", "value", "price")

COLLECTION_PARAMS = (
    "category",
    "categorySlug",
    "category_slug",
    "collection",
    "collectionSlug",
    "categories",
    "cat",
)

#: (style, position param, size param) tried in order.
PAGING_CANDIDATES = (
    ("offset", "offset", "limit"),
    ("offset", "skip", "limit"),
    ("offset", "skip", "take"),
    ("page", "page", "limit"),
    ("page", "page", "per_page"),
    ("page", "page", "pageSize"),
    ("page", "page", "size"),
)

_SCRIPT_RE = re.compile(r'<script[^>]+src="([^"]+)"', re.I)
_API_STRING_RE = re.compile(r"""["'`](/api/[A-Za-z0-9_/-]*products?)["'`?]""")
_COLLECTION_LINK_RE = re.compile(
    r'href="/(?:collections?|categor(?:y|ies)|product-category|c)/([a-z0-9][a-z0-9-]*)"',
    re.I,
)
_URL_TEMPLATE_RE = re.compile(
    r"`(/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)/\$\{[A-Za-z_$][\w$]*\.(\w+)\}`"
)


def _strip_query(url: str, drop: set[str]) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in drop]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _looks_like_products(items) -> bool:
    if not isinstance(items, list) or not items:
        return False
    sample = [i for i in items[:SAMPLE_SIZE] if isinstance(i, dict)]
    if not sample:
        return False
    return bool(
        _pick_key(sample, FIELD_CANDIDATES["price"])
        and _pick_key(sample, FIELD_CANDIDATES["title"])
    )


def find_items_path(body) -> str | None:
    """Dotted path to the product list in an API response, if one is there."""
    if _looks_like_products(body):
        return ""
    if not isinstance(body, dict):
        return None
    keys = sorted(body, key=lambda k: (k not in _LIST_KEYS, k))
    for key in keys:
        if _looks_like_products(body[key]):
            return key
    for key in keys:
        if isinstance(body[key], dict):
            inner = find_items_path(body[key])
            if inner:
                return f"{key}.{inner}"
    return None


def find_total_path(body, items_path: str) -> str:
    if not isinstance(body, dict):
        return ""
    parent = items_path.rsplit(".", 1)[0] if "." in items_path else ""
    for scope in dict.fromkeys([parent, "", "meta", "pagination", "pageInfo"]):
        node = get_path(body, scope)
        if not isinstance(node, dict):
            continue
        for key in _TOTAL_KEYS:
            if isinstance(node.get(key), int) and not isinstance(node.get(key), bool):
                return f"{scope}.{key}" if scope else key
    return ""


def _pick_key(sample: list[dict], candidates) -> str | None:
    """First candidate key (case-insensitive) that most sample items carry."""
    for cand in candidates:
        hits = Counter()
        for item in sample:
            for key in item:
                if key.lower() == cand.lower() and item[key] is not None:
                    hits[key] += 1
        if hits:
            key, n = hits.most_common(1)[0]
            if n * 2 >= len(sample):
                return key
    return None


def guess_fields(items: list, url_template: str | None = None) -> dict:
    sample = [i for i in items[:SAMPLE_SIZE] if isinstance(i, dict)]
    fields = {}
    for name, candidates in FIELD_CANDIDATES.items():
        key = _pick_key(sample, candidates)
        if not key:
            fields[name] = ""
            continue
        value = next((i[key] for i in sample if i.get(key) is not None), None)
        if name in ("price", "sale_price", "compare_at") and isinstance(value, dict):
            nested = next((n for n in _NESTED_PRICE if n in value), None)
            key = f"{key}.{nested}" if nested else ""
        elif name == "image":
            key = _image_path(key, value)
        elif name == "url" and not (
            isinstance(value, str) and (value.startswith("/") or "://" in value)
        ):
            key = ""
        fields[name] = key

    if fields["sale_price"] == fields["price"]:
        fields["sale_price"] = ""
    if not fields["url"]:
        handle = fields["handle"]
        if url_template and handle:
            fields["url"] = f"{url_template}/{{{handle}}}"
        elif handle:
            fields["url"] = f"/products/{{{handle}}}"
    return fields


def _image_path(key: str, value) -> str:
    if isinstance(value, list):
        key, value = f"{key}.0", value[0] if value else None
    if isinstance(value, dict):
        return f"{key}.url" if "url" in value else f"{key}.src"
    return key


def guess_url_template(scripts: list[str], handle_key: str) -> str | None:
    """Most common `/path/${x.<handle>}` route in the storefront's bundles.
    Category pages are keyed by slug too, so a route naming products wins."""
    counts: Counter = Counter()
    for text in scripts:
        for path, field in _URL_TEMPLATE_RE.findall(text):
            if field == handle_key:
                counts[path] += 1
    product = Counter({p: n for p, n in counts.items() if "product" in p.lower()})
    best = (product or counts).most_common(1)
    return best[0][0] if best else None


async def _get_json(client: httpx.AsyncClient, url: str, params: dict | None = None):
    try:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def _ids(client, url, params, items_path, id_key) -> list | None:
    body = await _get_json(client, url, params)
    items = get_path(body, items_path) if body is not None else None
    if not isinstance(items, list):
        return None
    return [get_path(i, id_key) if id_key else repr(i) for i in items]


async def probe_paging(
    client: httpx.AsyncClient, url: str, items_path: str, id_key: str, size: int
) -> tuple[str, str, str] | None:
    """(style, position param, size param) of the first scheme that really pages."""
    for style, pos, size_param in PAGING_CANDIDATES:
        start = 0 if style == "offset" else 1
        first = await _ids(
            client, url, {size_param: size, pos: start}, items_path, id_key
        )
        if not first:
            continue
        nxt = len(first) if style == "offset" else 2
        second = await _ids(
            client, url, {size_param: size, pos: nxt}, items_path, id_key
        )
        if second and not set(map(repr, second)) & set(map(repr, first)):
            return style, pos, size_param
    return None


async def probe_collection(
    client: httpx.AsyncClient, url: str, cfg: dict, slug: str, unfiltered: dict
) -> str | None:
    """The query param that narrows the list to one collection, if any does."""
    for param in COLLECTION_PARAMS:
        body = await _get_json(client, url, {param: slug})
        items = get_path(body, cfg["items_path"]) if body is not None else None
        if not isinstance(items, list) or not items:
            continue
        total = total_of(body, cfg)
        if total is not None and unfiltered["total"] is not None:
            if total < unfiltered["total"]:
                return param
        elif [repr(i) for i in items] != unfiltered["items"]:
            return param
    return None


async def inspect_endpoint(
    client: httpx.AsyncClient,
    api_url: str,
    base_url: str,
    scripts: list[str] | None = None,
    page: str = "",
) -> dict | None:
    """A guessed config for one candidate URL, or None if it isn't a product list."""
    body = await _get_json(client, api_url)
    if body is None:
        return None
    items_path = find_items_path(body)
    if items_path is None:
        return None
    items = get_path(body, items_path)
    total_path = find_total_path(body, items_path)

    handle = guess_fields(items)["handle"]
    template = guess_url_template(scripts or [], handle) if handle else None
    fields = guess_fields(items, template)

    cfg = normalize_config({**DEFAULT_CONFIG, "fields": fields})
    cfg["items_path"] = items_path
    cfg["total_path"] = total_path

    total = total_of(body, cfg)
    paged_params = {k for _, p, s in PAGING_CANDIDATES for k in (p, s)}
    endpoint = _strip_query(api_url, paged_params)
    if endpoint == base_url or endpoint.startswith(f"{base_url}/"):
        endpoint = endpoint[len(base_url) :] or "/"
    cfg["endpoint"] = endpoint

    if total is None or len(items) < total:
        found = await probe_paging(
            client, urljoin(f"{base_url}/", endpoint), items_path, fields["id"], 100
        )
        if found:
            style, pos, size_param = found
            cfg.update(paging=style, page_param=pos, size_param=size_param)

    slug = next(iter(_COLLECTION_LINK_RE.findall(page)), None)
    if slug:
        url = urljoin(f"{base_url}/", endpoint)
        # The pasted URL may carry its own limit; compare like with like.
        base_body = await _get_json(client, url)
        base_items = get_path(base_body, items_path) if base_body is not None else None
        if isinstance(base_items, list):
            unfiltered = {
                "total": total_of(base_body, cfg),
                "items": [repr(i) for i in base_items],
            }
            cfg["collection_param"] = (
                await probe_collection(client, url, cfg, slug, unfiltered) or ""
            )
    return cfg


async def _scripts(client: httpx.AsyncClient, base_url: str) -> tuple[str, list[str]]:
    """The homepage HTML and the text of its same-site scripts."""
    try:
        r = await client.get(f"{base_url}/")
        page = r.text if r.is_success else ""
    except Exception:
        return "", []
    host = urlsplit(base_url).netloc
    srcs = []
    for src in _SCRIPT_RE.findall(page):
        full = urljoin(f"{base_url}/", src)
        if urlsplit(full).netloc == host and full not in srcs:
            srcs.append(full)

    async def text(url):
        try:
            r = await client.get(url)
            return r.text if r.is_success else ""
        except Exception:
            return ""

    bodies = await asyncio.gather(*(text(u) for u in srcs[:MAX_SCRIPTS]))
    return page, [b for b in bodies if b]


def candidate_endpoints(page: str, scripts: list[str]) -> list[str]:
    found: Counter = Counter()
    for text in [page, *scripts]:
        for path in _API_STRING_RE.findall(text):
            found[path] += 1
    ranked = [p for p, _ in found.most_common()]
    return list(dict.fromkeys([*ranked, *COMMON_ENDPOINTS]))


async def preview(
    client: httpx.AsyncClient,
    cfg: dict,
    base_url: str,
    collection_path: str = "/",
) -> dict:
    """First page through `cfg`, mapped, with warnings about what looks off."""
    raw, total = await fetch_all(client, cfg, base_url, collection_path, max_pages=1)
    mapped = [map_item(i, cfg, base_url) for i in raw]
    rows = [m for m in mapped if m]
    warnings = []
    if not raw:
        warnings.append("The API returned no items.")
    elif len(rows) < len(raw):
        warnings.append(
            f"{len(raw) - len(rows)} of {len(raw)} items have no usable id or price."
        )
    if rows and not any(r["url"] for r in rows):
        warnings.append("No product links — set the URL field or template.")
    if cfg["paging"] == "none" and total is not None and len(raw) < total:
        warnings.append(
            f"Only {len(raw)} of {total} items come back and no paging is set."
        )
    return {
        "config": cfg,
        "total": total,
        "samples": [_sample(r) for r in rows[:SAMPLE_SIZE]],
        "warnings": warnings,
    }


def _sample(row: dict) -> dict:
    v = row["variants"][0]
    return {
        "title": row["title"],
        "url": row["url"],
        "image_url": row["image_url"],
        "price": v["price"],
        "compare_at_price": v["compare_at_price"],
        "available": v["available"],
        "preorder": v["preorder"],
    }


async def discover(
    client: httpx.AsyncClient, base_url: str, api_url: str | None = None
) -> dict | None:
    """Find and inspect the product API. `api_url` skips the search."""
    page, scripts = await _scripts(client, base_url)
    candidates = [api_url] if api_url else candidate_endpoints(page, scripts)
    for candidate in candidates:
        cfg = await inspect_endpoint(
            client, urljoin(f"{base_url}/", candidate), base_url, scripts, page
        )
        if cfg:
            return cfg
    return None
