"""OpenCart adapter, reading the product cards a category page server-renders.

OpenCart has no keyless catalog API. Category pages honour `limit` and `page`,
so a large `limit` reads most categories in one request.
"""

import asyncio
import html
import re
from urllib.parse import urlsplit

import httpx

from .base import StoreAdapter, store_cfg
from .woocommerce import USER_AGENT

PAGE_LIMIT = 100
RETRIES = 5
BACKOFF_SEC = 30
MAX_WAIT_SEC = 900
#: Gap between pages once the shop has pushed back, doubling per refusal.
THROTTLED_DELAY_SEC = 5
MAX_DELAY_SEC = 60
#: What rate limits, soft bans and an overloaded origin or CDN answer with.
RETRY_STATUSES = {403, 408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}

_CARD_RE = re.compile(r'<div[^>]*class="product-layout\b([^"]*)"[^>]*>')
_GRID_START = 'class="main-products'
_GRID_END = 'class="pagination"'
_ID_RES = (
    re.compile(r'data-product-id="(\d+)"'),
    re.compile(r"cart\.add\('(\d+)'"),
    re.compile(r"product_id=(\d+)"),
)
_NAME_RE = re.compile(
    r'(?:class="name"[^>]*>|<h4>)\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL
)
_IMG_RE = re.compile(r'<img[^>]*\ssrc="([^"]+)"')
_PRICE_BLOCK_RE = re.compile(
    r'class="price"[^>]*>(.*?)(?:<span class="price-tax"|</p>)', re.DOTALL
)
_PAGER_RE = re.compile(r'<ul class="pagination[^"]*".*?</ul>', re.DOTALL)
_PAGE_LINK_RE = re.compile(r"[?&;]page=(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"\d[\d.,\s]*")


def _text(fragment: str) -> str:
    return html.unescape(_TAG_RE.sub("", fragment)).strip()


def parse_price(text: str | None) -> float | None:
    """A display price like "₹ 1,300.00" or "13,50 €" as a float."""
    match = _NUMBER_RE.search(text or "")
    if not match:
        return None
    s = re.sub(r"\s", "", match.group()).rstrip(".,")
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal == "," else ",", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{2}", s) else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _span(card: str, cls: str) -> str | None:
    match = re.search(rf'<span class="{cls}"[^>]*>(.*?)</span>', card, re.DOTALL)
    return _text(match.group(1)) if match else None


def _prices(card: str) -> tuple[float | None, float | None]:
    price = parse_price(_span(card, "price-new") or _span(card, "price-normal"))
    if price is None:
        block = _PRICE_BLOCK_RE.search(card)
        price = parse_price(_text(block.group(1))) if block else None
    old = parse_price(_span(card, "price-old"))
    compare_at = old if (price is not None and old and old > price) else None
    return price, compare_at


def _handle(url: str) -> str | None:
    """SEO slug of a product URL; None for `index.php?route=...` links."""
    parts = urlsplit(url)
    slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
    return None if parts.query or not slug or slug.endswith(".php") else slug


def parse_cards(page_html: str) -> list[dict]:
    """Product cards of a listing page, limited to the main grid when marked."""
    start = max(page_html.find(_GRID_START), 0)
    end = page_html.find(_GRID_END, start)
    region = page_html[start : end if end != -1 else len(page_html)]

    matches = list(_CARD_RE.finditer(region))
    cards = []
    for i, match in enumerate(matches):
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(region)
        cards.append(
            {"classes": match.group(1).split(), "html": region[match.start() : stop]}
        )
    return cards


def map_card(card: dict) -> dict | None:
    """Listing card to the sync dict shape. None without an id, name or price."""
    body = card["html"]
    external_id = next((m.group(1) for rx in _ID_RES if (m := rx.search(body))), None)
    name = _NAME_RE.search(body)
    price, compare_at = _prices(body)
    if external_id is None or name is None or price is None:
        return None

    url = html.unescape(name.group(1))
    image = _IMG_RE.search(body)
    return {
        "external_id": external_id,
        "title": _text(name.group(2)),
        "handle": _handle(url),
        "url": url,
        "image_url": html.unescape(image.group(1)) if image else None,
        "variants": [
            {
                # Listings don't price options, so one line per product.
                "variant_id": external_id,
                "variant_title": "Default",
                "price": price,
                "compare_at_price": compare_at,
                # Themes without a stock class can't say, so assume buyable.
                "available": "out-of-stock" not in card["classes"],
            }
        ],
    }


def has_next_page(page_html: str, page: int) -> bool:
    """Whether the pager links past `page`; card counts can't tell, as pages
    may render fewer cards than `limit` mid-catalog."""
    pager = _PAGER_RE.search(page_html)
    return bool(pager) and any(
        int(n) > page for n in _PAGE_LINK_RE.findall(pager.group())
    )


def is_opencart(response: httpx.Response) -> bool:
    """OpenCart sets its session cookie and serves themes from `catalog/view/`."""
    return "OCSESSID" in response.cookies or "catalog/view/" in response.text


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["retry-after"]), MAX_WAIT_SEC)
    except (KeyError, ValueError):
        return None


class OpenCartAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        base = self.store.base_url.rstrip("/")
        # Non-SEO stores list categories as `index.php?route=...&path=N`.
        url = httpx.URL(f"{base}{self.collection_path.rstrip('/')}")
        self._timeout = store_cfg(self.store, "timeout_sec")
        self._delay = store_cfg(self.store, "request_delay_sec")

        results: dict[str, dict] = {}
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            page = 1
            while True:
                r, cards = await self._fetch_page(
                    client, url.copy_merge_params({"limit": PAGE_LIMIT, "page": page})
                )
                # Raised past page 1 too, so a bad page fails the sync loudly
                # rather than silently dropping the rest of the catalog.
                if not cards:
                    raise ValueError(
                        f"no product grid on page {page}: {self.collection_path}"
                    )
                fresh = 0
                for card in cards:
                    mapped = map_card(card)
                    if mapped and mapped["external_id"] not in results:
                        results[mapped["external_id"]] = mapped
                        fresh += 1
                # Some themes repeat the last page past the end.
                if not fresh or not has_next_page(r.text, page):
                    break
                page += 1
                if self._delay:
                    await asyncio.sleep(self._delay)

        return list(results.values())

    async def _fetch_page(
        self, client: httpx.AsyncClient, url: httpx.URL
    ) -> tuple[httpx.Response, list[dict]]:
        """GET a listing page, backing off while the shop times out or blocks us.
        Each refusal also slows the rest of the walk; pacing lifts soft bans."""
        problem, wait = "", 0.0
        for attempt in range(RETRIES + 1):
            if attempt:
                await asyncio.sleep(wait)
            wait = BACKOFF_SEC * 2**attempt
            try:
                # A slow origin gets a longer cut-off on each try.
                r = await client.get(url, timeout=self._timeout * (attempt + 1))
            except httpx.TransportError as e:
                problem = type(e).__name__
            else:
                if r.status_code in RETRY_STATUSES:
                    problem = f"HTTP {r.status_code}"
                    wait = _retry_after(r) or wait
                else:
                    r.raise_for_status()
                    cards = parse_cards(r.text)
                    if cards or is_opencart(r):
                        return r, cards
                    problem = "challenge or block page"
            self._delay = min(max(self._delay * 2, THROTTLED_DELAY_SEC), MAX_DELAY_SEC)

        raise RuntimeError(
            f"shop kept refusing after {RETRIES + 1} tries ({problem}): {url}"
        )
