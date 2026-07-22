"""Catalog data-access layer.

Single source of truth for the "enriched product" read model: browse,
search, home dashboard, all feeds. Latest-snapshot join, BGG enrichment,
and override merging live here so no two endpoints can drift.
"""

from __future__ import annotations

import json

from sqlalchemy import case, func
from sqlmodel import Session, select

from ..filter_engine import (
    Condition,
    FilterNode,
    SortSpec,
    apply_filter,
    apply_sorts,
    build_field_registry,
    filter_uses_field,
)
from ..models import (
    BggCache,
    PriceSnapshot,
    Product,
    ProductOverride,
    Store,
    WatchlistItem,
)
from ..text_search import rank_titles

# ---------------------------------------------------------------------------
# Subqueries
# ---------------------------------------------------------------------------


def _latest_snapshot_subq():
    """(product_id, max_date) for the most recent snapshot per product."""
    return (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )


def _first_seen_subq():
    """(product_id, first_date) — when product was first tracked."""
    return (
        select(
            PriceSnapshot.product_id,
            func.min(PriceSnapshot.recorded_at).label("first_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )


def _prev_snapshot_subq():
    """(product_id, prev_price, prev_available) — second-most-recent snapshot."""
    ranked = select(
        PriceSnapshot.product_id,
        PriceSnapshot.price.label("prev_price"),
        PriceSnapshot.available.label("prev_available"),
        func.row_number()
        .over(
            partition_by=PriceSnapshot.product_id,
            order_by=PriceSnapshot.recorded_at.desc(),
        )
        .label("rn"),
    ).subquery()
    return select(ranked).where(ranked.c.rn == 2).subquery()


def _bgg_subq():
    """BGG numeric fields pulled from cached JSON."""
    return select(
        BggCache.bgg_id,
        func.json_extract(BggCache.data, "$.bgg_rating").label("bgg_rating"),
        func.json_extract(BggCache.data, "$.avg_rating").label("avg_rating"),
        func.json_extract(BggCache.data, "$.avg_weight").label("avg_weight"),
        func.json_extract(BggCache.data, "$.rank").label("rank"),
    ).subquery()


# ---------------------------------------------------------------------------
# Base join + registry helper
# ---------------------------------------------------------------------------


def _build_joined_stmt(latest, bgg, first_seen, prev_snap, watchlist):
    return (
        select(Product, PriceSnapshot)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .join(bgg, Product.bgg_id == bgg.c.bgg_id, isouter=True)
        .join(first_seen, Product.id == first_seen.c.product_id, isouter=True)
        .join(prev_snap, Product.id == prev_snap.c.product_id, isouter=True)
        .join(watchlist, Product.id == watchlist.c.product_id, isouter=True)
    )


def _watchlist_subq():
    """Distinct product_ids on the watchlist. Removal is a soft delete
    (active=False), so inactive rows must not count as watched."""
    return (
        select(WatchlistItem.product_id)
        .where(WatchlistItem.active)
        .distinct()
        .subquery()
    )


def _subqueries():
    latest = _latest_snapshot_subq()
    bgg = _bgg_subq()
    first_seen = _first_seen_subq()
    prev_snap = _prev_snapshot_subq()
    watchlist = _watchlist_subq()
    return latest, bgg, first_seen, prev_snap, watchlist


def get_field_registry():
    """Registry for introspection endpoint — subqueries are never executed."""
    _, bgg, first_seen, prev_snap, watchlist = _subqueries()
    return build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
    )


# ---------------------------------------------------------------------------
# Enrichment — (product, snapshot) pairs → card dicts
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
    """Batch-enrich (product, latest_snapshot) pairs into card dicts."""
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

    # Batch-fetch last 12 price snapshots per product for sparkline display.
    histories: dict[int, list[dict]] = {}
    if product_ids:
        rn_col = (
            func.row_number()
            .over(
                partition_by=PriceSnapshot.product_id,
                order_by=PriceSnapshot.recorded_at.desc(),
            )
            .label("rn")
        )
        subq = (
            select(PriceSnapshot.product_id, PriceSnapshot.price, rn_col)
            .where(PriceSnapshot.product_id.in_(product_ids))
            .subquery()
        )
        for pid, price in session.exec(
            select(subq.c.product_id, subq.c.price).where(subq.c.rn <= 12)
        ):
            histories.setdefault(int(pid), []).append({"price": float(price)})

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
            "price_history": histories.get(product.id, []),
        }
        if extra and product.id in extra:
            card.update(extra[product.id])
        cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------

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


def query_products(
    session: Session,
    *,
    filter_node: FilterNode | None = None,
    sorts: list[SortSpec] | None = None,
    page: int = 1,
    limit: int = 48,
    include_hidden: bool = False,
) -> list[tuple[Product, PriceSnapshot | None]]:
    """Filtered, sorted, paginated (product, latest_snapshot) pairs."""
    latest, bgg, first_seen, prev_snap, watchlist = _subqueries()
    registry = build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
    )
    stmt = _build_joined_stmt(latest, bgg, first_seen, prev_snap, watchlist)

    filter_on_hidden = filter_node is not None and filter_uses_field(
        filter_node, "hidden"
    )
    if not include_hidden and not filter_on_hidden:
        stmt = stmt.where(Product.hidden == False)  # noqa: E712

    if filter_node is not None:
        stmt = stmt.where(apply_filter(filter_node, registry))

    if sorts:
        stmt = apply_sorts(stmt, sorts, registry)
    else:
        stmt = stmt.order_by(Product.title.asc())

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    return [(r[0], r[1]) for r in rows]


def count_products(
    session: Session,
    *,
    filter_node: FilterNode | None = None,
    include_hidden: bool = False,
) -> int:
    """Total matching row count (for pagination)."""
    latest, bgg, first_seen, prev_snap, watchlist = _subqueries()
    registry = build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
    )
    stmt = (
        select(func.count())
        .select_from(Product)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .join(bgg, Product.bgg_id == bgg.c.bgg_id, isouter=True)
        .join(first_seen, Product.id == first_seen.c.product_id, isouter=True)
        .join(prev_snap, Product.id == prev_snap.c.product_id, isouter=True)
        .join(watchlist, Product.id == watchlist.c.product_id, isouter=True)
    )
    filter_on_hidden = filter_node is not None and filter_uses_field(
        filter_node, "hidden"
    )
    if not include_hidden and not filter_on_hidden:
        stmt = stmt.where(Product.hidden == False)  # noqa: E712
    if filter_node is not None:
        stmt = stmt.where(apply_filter(filter_node, registry))
    return session.exec(stmt).one()


# ---------------------------------------------------------------------------
# Feeds (used by old catalog routes — kept for search bar + hidden page)
# ---------------------------------------------------------------------------


def _ranked_snapshots_subq():
    """Each snapshot with recency rank (1 = latest) per product."""
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
    """Products whose latest price < their previous recorded price."""
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
        .where(Product.hidden == False)  # noqa: E712
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
    rows = query_products(
        session,
        sorts=[SortSpec(field="first_seen", dir="desc")],
        page=page,
        limit=limit,
    )
    return make_cards(session, rows)


def top_discounts(session: Session, *, page: int = 1, limit: int = 12) -> list[dict]:
    """Largest current % discount."""
    rows = query_products(
        session,
        filter_node=Condition(field="discount_pct", op="gt", value=0),
        sorts=[SortSpec(field="discount_pct", dir="desc")],
        page=page,
        limit=limit,
    )
    cards = make_cards(session, rows)
    return [c for c in cards if (c["discount_pct"] or 0) > 0]


def _rows_by_ids(
    session: Session, ids: list[int]
) -> list[tuple[Product, PriceSnapshot | None]]:
    """(product, latest_snapshot) pairs for the given ids, in the given order."""
    if not ids:
        return []
    latest, bgg, first_seen, prev_snap, watchlist = _subqueries()
    stmt = _build_joined_stmt(latest, bgg, first_seen, prev_snap, watchlist).where(
        Product.id.in_(ids)
    )
    by_id = {r[0].id: (r[0], r[1]) for r in session.exec(stmt).all()}
    return [by_id[i] for i in ids if i in by_id]


def search(session: Session, *, q: str, limit: int = 24) -> list[dict]:
    """Title search for the global search bar.

    Ranked and typo-tolerant: scoring runs in Python over the candidate titles
    because SQLite `LIKE` can only do substrings, which makes a single typo
    return nothing at all. See app.text_search.
    """
    if not q or not q.strip():
        return []
    candidates = session.exec(
        select(Product.id, Product.title).where(Product.hidden == False)  # noqa: E712
    ).all()
    ranked = rank_titles(q, [(r[0], r[1]) for r in candidates], limit=limit)
    return make_cards(session, _rows_by_ids(session, [pid for pid, _ in ranked]))


def hidden_products(session: Session, *, page: int = 1, limit: int = 48) -> list[dict]:
    """Enriched cards for hidden products."""
    latest = _latest_snapshot_subq()
    stmt = (
        select(Product, PriceSnapshot)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .where(Product.hidden == True)  # noqa: E712
        .order_by(Product.updated_at.desc())
    )
    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    return make_cards(session, [(r[0], r[1]) for r in rows])


def enabled_stores(session: Session) -> list[Store]:
    return session.exec(select(Store).where(Store.enabled)).all()
