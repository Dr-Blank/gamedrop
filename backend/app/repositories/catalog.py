"""Catalog data-access layer.

Single source of truth for the "enriched product" read model used by browse,
search, the home dashboard and every feed. Keeping the latest-snapshot join,
BGG enrichment and override merging here means routes stay thin and no two
endpoints can drift in how they shape a product card.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import case, func, text
from sqlmodel import Session, select

from ..models import BggCache, PriceSnapshot, Product, ProductOverride, Store

# ---------------------------------------------------------------------------
# Sort catalogue (shared by browse + feeds)
# ---------------------------------------------------------------------------

SORT_OPTIONS = {
    "title": "Name (A–Z)",
    "price_asc": "Price ↑",
    "price_desc": "Price ↓",
    "newest": "Newly added",
    "price_changed": "Price changed recently",
    "discount_pct": "Biggest % discount",
    "discount_abs": "Biggest absolute discount",
    "bgg_rating": "BGG rating ↓",
    "value": "Best value (price ÷ rating)",
    "value_weight": "Price per complexity (÷ weight)",
    "price_rating_rank": "Price × rank score",
}


@dataclass(frozen=True)
class CatalogFilters:
    q: str | None = None
    store_id: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    in_stock: bool | None = None
    has_bgg: bool | None = None
    min_bgg_rating: float | None = None


# ---------------------------------------------------------------------------
# Reusable subqueries
# ---------------------------------------------------------------------------


def _latest_snapshot_subq():
    """(product_id, max_date) for the most recent snapshot of each product."""
    return (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )


def _first_seen_subq():
    """(product_id, first_date) — proxy for when a product was first tracked."""
    return (
        select(
            PriceSnapshot.product_id,
            func.min(PriceSnapshot.recorded_at).label("first_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )


def _bgg_subq():
    """BGG numeric fields pulled out of the cached JSON for filtering/sorting."""
    return select(
        BggCache.bgg_id,
        func.json_extract(BggCache.data, "$.bgg_rating").label("bgg_rating"),
        func.json_extract(BggCache.data, "$.avg_rating").label("avg_rating"),
        func.json_extract(BggCache.data, "$.avg_weight").label("avg_weight"),
        func.json_extract(BggCache.data, "$.rank").label("rank"),
    ).subquery()


_DISCOUNT_PCT = case(
    (
        (PriceSnapshot.compare_at_price > PriceSnapshot.price)
        & (PriceSnapshot.compare_at_price > 0),
        (PriceSnapshot.compare_at_price - PriceSnapshot.price)
        / PriceSnapshot.compare_at_price,
    ),
    else_=0,
)
_DISCOUNT_ABS = case(
    (
        PriceSnapshot.compare_at_price > PriceSnapshot.price,
        PriceSnapshot.compare_at_price - PriceSnapshot.price,
    ),
    else_=0,
)


# ---------------------------------------------------------------------------
# Enrichment — turn ORM rows into card dicts (batched, no N+1)
# ---------------------------------------------------------------------------


def _parse_bgg(cache: BggCache | None, bgg_id: int | None) -> dict | None:
    if not cache or not bgg_id:
        return None
    try:
        parsed = json.loads(cache.data)
    except (json.JSONDecodeError, TypeError):
        return None
    return {
        "bgg_id": bgg_id,
        "name": parsed.get("name"),
        "avg_rating": parsed.get("avg_rating"),
        "bgg_rating": parsed.get("bgg_rating"),
        "rank": parsed.get("rank"),
        "avg_weight": parsed.get("avg_weight"),
        "thumbnail": parsed.get("thumbnail"),
        "bgg_url": parsed.get("bgg_url"),
    }


def _discount_pct(price: float | None, compare_at: float | None) -> float | None:
    if price and compare_at and compare_at > price:
        return round((compare_at - price) / compare_at * 100, 1)
    return None


def make_cards(
    session: Session,
    items: list[tuple[Product, PriceSnapshot | None]],
    *,
    extra: dict[int, dict] | None = None,
) -> list[dict]:
    """Batch-enrich (product, latest_snapshot) pairs into card dicts.

    `extra` lets feeds attach per-product fields (e.g. previous_price) keyed by
    product id. Loads BGG cache + overrides in two queries total.
    """
    products = [p for p, _ in items]
    product_ids = [p.id for p in products if p.id is not None]
    bgg_ids = {p.bgg_id for p in products if p.bgg_id}

    overrides: dict[int, ProductOverride] = {}
    if product_ids:
        for ov in session.exec(
            select(ProductOverride).where(ProductOverride.product_id.in_(product_ids))
        ):
            overrides[ov.product_id] = ov

    bgg_cache: dict[int, BggCache] = {}
    if bgg_ids:
        for c in session.exec(select(BggCache).where(BggCache.bgg_id.in_(bgg_ids))):
            bgg_cache[c.bgg_id] = c

    cards = []
    for product, snap in items:
        price = snap.price if snap else None
        cap = snap.compare_at_price if snap else None
        card = {
            "product": product,
            "latest_price": snap,
            "bgg": _parse_bgg(bgg_cache.get(product.bgg_id), product.bgg_id),
            "override": overrides.get(product.id) if product.id else None,
            "discount_pct": _discount_pct(price, cap),
        }
        if extra and product.id in extra:
            card.update(extra[product.id])
        cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Browse / filter / sort
# ---------------------------------------------------------------------------


def query_products(
    session: Session,
    *,
    filters: CatalogFilters = CatalogFilters(),
    sort: str = "title",
    page: int = 1,
    limit: int = 48,
) -> list[tuple[Product, PriceSnapshot | None]]:
    """Filtered, sorted, paginated (product, latest_snapshot) pairs."""
    latest = _latest_snapshot_subq()
    bgg = _bgg_subq()

    stmt = (
        select(Product, PriceSnapshot)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .join(bgg, Product.bgg_id == bgg.c.bgg_id, isouter=True)
    )

    if filters.q:
        stmt = stmt.where(Product.title.ilike(f"%{filters.q}%"))
    if filters.store_id:
        stmt = stmt.where(Product.store_id == filters.store_id)
    if filters.in_stock is not None:
        stmt = stmt.where(PriceSnapshot.available == filters.in_stock)
    if filters.has_bgg is True:
        stmt = stmt.where(Product.bgg_id.is_not(None))
    if filters.has_bgg is False:
        stmt = stmt.where(Product.bgg_id.is_(None))
    if filters.min_price is not None:
        stmt = stmt.where(PriceSnapshot.price >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(PriceSnapshot.price <= filters.max_price)
    if filters.min_bgg_rating is not None:
        stmt = stmt.where(bgg.c.bgg_rating >= filters.min_bgg_rating)

    stmt = _apply_sort(stmt, sort, bgg)

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    return [(r[0], r[1]) for r in rows]


def _apply_sort(stmt, sort: str, bgg):
    match sort:
        case "price_asc":
            return stmt.order_by(PriceSnapshot.price.asc())
        case "price_desc":
            return stmt.order_by(PriceSnapshot.price.desc())
        case "newest":
            return stmt.order_by(Product.updated_at.desc())
        case "price_changed":
            return stmt.order_by(PriceSnapshot.recorded_at.desc())
        case "discount_pct":
            return stmt.order_by(_DISCOUNT_PCT.desc())
        case "discount_abs":
            return stmt.order_by(_DISCOUNT_ABS.desc())
        case "bgg_rating":
            return stmt.order_by(bgg.c.bgg_rating.desc().nulls_last())
        case "value":
            expr = case(
                (bgg.c.bgg_rating > 0, PriceSnapshot.price / bgg.c.bgg_rating),
                else_=text("9999999"),
            )
            return stmt.order_by(expr.asc())
        case "value_weight":
            expr = case(
                (bgg.c.avg_weight > 0, PriceSnapshot.price / bgg.c.avg_weight),
                else_=text("9999999"),
            )
            return stmt.order_by(expr.asc())
        case "price_rating_rank":
            expr = case(
                (
                    (bgg.c.bgg_rating > 0)
                    & (bgg.c.rank > 0)
                    & (PriceSnapshot.price > 0),
                    bgg.c.bgg_rating / (bgg.c.rank * PriceSnapshot.price),
                ),
                else_=0,
            )
            return stmt.order_by(expr.desc())
        case _:
            return stmt.order_by(Product.title.asc())


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def _ranked_snapshots_subq():
    """Each snapshot tagged with its recency rank within its product (1 = latest)."""
    return select(
        PriceSnapshot.product_id,
        PriceSnapshot.price,
        PriceSnapshot.compare_at_price,
        PriceSnapshot.available,
        PriceSnapshot.recorded_at,
        func.row_number()
        .over(
            partition_by=PriceSnapshot.product_id,
            order_by=PriceSnapshot.recorded_at.desc(),
        )
        .label("rn"),
    ).subquery()


def price_drops(
    session: Session, *, page: int = 1, limit: int = 12, in_stock_only: bool = False
) -> list[dict]:
    """Products whose latest price is below their previous recorded price."""
    ranked = _ranked_snapshots_subq()
    latest = select(ranked).where(ranked.c.rn == 1).subquery()
    prev = select(ranked).where(ranked.c.rn == 2).subquery()

    drop_pct = (prev.c.price - latest.c.price) / prev.c.price

    stmt = (
        select(Product, PriceSnapshot, prev.c.price.label("previous_price"))
        .join(latest, Product.id == latest.c.product_id)
        .join(prev, Product.id == prev.c.product_id)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == Product.id)
            & (PriceSnapshot.recorded_at == latest.c.recorded_at),
        )
        .where(latest.c.price < prev.c.price)
    )
    if in_stock_only:
        stmt = stmt.where(latest.c.available == True)  # noqa: E712
    stmt = stmt.order_by(drop_pct.desc())

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    extra = {r[0].id: {"previous_price": r[2]} for r in rows}
    return make_cards(session, [(r[0], r[1]) for r in rows], extra=extra)


def new_additions(session: Session, *, page: int = 1, limit: int = 12) -> list[dict]:
    """Most recently first-seen products."""
    first_seen = _first_seen_subq()
    latest = _latest_snapshot_subq()

    stmt = (
        select(Product, PriceSnapshot)
        .join(first_seen, Product.id == first_seen.c.product_id)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == Product.id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .order_by(first_seen.c.first_date.desc())
    )
    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    return make_cards(session, [(r[0], r[1]) for r in rows])


def top_discounts(session: Session, *, page: int = 1, limit: int = 12) -> list[dict]:
    """Largest current % discount (compare-at vs price) on the latest snapshot."""
    rows = query_products(
        session,
        filters=CatalogFilters(),
        sort="discount_pct",
        page=page,
        limit=limit,
    )
    # query_products already orders by discount; drop zero-discount tail.
    cards = make_cards(session, rows)
    return [c for c in cards if (c["discount_pct"] or 0) > 0]


def search(session: Session, *, q: str, limit: int = 24) -> list[dict]:
    """Title search returning enriched cards (used by the global search bar)."""
    if not q or not q.strip():
        return []
    rows = query_products(
        session, filters=CatalogFilters(q=q.strip()), sort="title", limit=limit
    )
    return make_cards(session, rows)


def enabled_stores(session: Session) -> list[Store]:
    return session.exec(select(Store).where(Store.enabled)).all()
