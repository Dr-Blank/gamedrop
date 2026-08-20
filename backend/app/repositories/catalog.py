"""Catalog data-access layer.

Single source of truth for the "enriched card" read model: browse, search, home
dashboard, all feeds. A card joins a listing (`Product`) to the game it belongs
to (`Game`), so the name, BGG data and watch state come from the game while the
price comes from the shop.
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
    Game,
    PriceSnapshot,
    Product,
    ProductOverride,
    Store,
    WatchlistItem,
)
from ..text_search import rank_titles

#: (listing, latest snapshot, game) — what every read in here returns.
CatalogRow = tuple[Product, PriceSnapshot | None, Game]

# ---------------------------------------------------------------------------
# Subqueries
# ---------------------------------------------------------------------------


def _latest_snapshot_subq():
    """(product_id, max_date) for the most recent snapshot per listing."""
    return (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )


def _first_seen_subq():
    """(product_id, first_date) — when the listing was first tracked."""
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


def _watchlist_subq():
    """Distinct watched game ids. Removal is a soft delete (active=False), so
    inactive rows must not count as watched."""
    return (
        select(WatchlistItem.game_id).where(WatchlistItem.active).distinct().subquery()
    )


def _store_count_subq():
    """(game_id, store_count) — how many shops sell each game."""
    return (
        select(
            Product.game_id.label("game_id"),
            func.count(func.distinct(Product.store_id)).label("store_count"),
        )
        .group_by(Product.game_id)
        .subquery()
    )


# ---------------------------------------------------------------------------
# Base join + registry helper
# ---------------------------------------------------------------------------


def _build_joined_stmt(latest, bgg, first_seen, prev_snap, watchlist, store_count):
    return (
        select(Product, PriceSnapshot, Game)
        .join(Game, Product.game_id == Game.id)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .join(bgg, Game.bgg_id == bgg.c.bgg_id, isouter=True)
        .join(first_seen, Product.id == first_seen.c.product_id, isouter=True)
        .join(prev_snap, Product.id == prev_snap.c.product_id, isouter=True)
        .join(watchlist, Product.game_id == watchlist.c.game_id, isouter=True)
        .join(store_count, Product.game_id == store_count.c.game_id, isouter=True)
    )


def _subqueries():
    latest = _latest_snapshot_subq()
    bgg = _bgg_subq()
    first_seen = _first_seen_subq()
    prev_snap = _prev_snapshot_subq()
    watchlist = _watchlist_subq()
    store_count = _store_count_subq()
    return latest, bgg, first_seen, prev_snap, watchlist, store_count


def get_field_registry():
    """Registry for the introspection endpoint — subqueries are never executed."""
    _, bgg, first_seen, prev_snap, watchlist, store_count = _subqueries()
    return build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
        store_count_subq=store_count,
    )


# ---------------------------------------------------------------------------
# Enrichment — rows → card dicts
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


def _offer(product: Product, snap: PriceSnapshot | None, override) -> dict:
    """One shop's current offer, override-corrected."""
    price = snap.price if snap else None
    available = snap.available if snap else False
    if override is not None:
        if override.override_price is not None:
            price = override.override_price
        if override.override_available is not None:
            available = override.override_available
    return {
        "product_id": product.id,
        "store_id": product.store_id,
        "listing_title": product.title,
        "url": (override.url if override and override.url else product.url),
        "image_url": product.image_url,
        "price": price,
        "compare_at_price": snap.compare_at_price if snap else None,
        "available": bool(available),
        "recorded_at": snap.recorded_at if snap else None,
        "price_history": [],  # filled in by the batched history query
    }


def _offer_images(offers: list[dict]) -> list[dict]:
    """Distinct listing images, cheapest offer first.

    Identical URLs collapse, so a game whose shops share one publisher photo
    needs no carousel.
    """
    images: list[dict] = []
    seen: set[str] = set()
    for offer in offers:
        url = offer.get("image_url")
        if not url or url in seen:
            continue
        seen.add(url)
        images.append(
            {
                "url": url,
                "store_id": offer["store_id"],
                "product_id": offer["product_id"],
            }
        )
    return images


def _compare_summaries(session: Session, game_ids: set[int]) -> dict[int, dict]:
    """Cross-shop price comparison per game, keyed by game id.

    `cheapest` and `cheapest_in_stock` are separate: the lowest price is often
    the out-of-stock one, and showing only that number misleads.
    """
    if not game_ids:
        return {}

    latest = _latest_snapshot_subq()
    rows = session.exec(
        select(Product, PriceSnapshot)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .where(Product.game_id.in_(game_ids))
    ).all()

    listing_ids = [r[0].id for r in rows if r[0].id is not None]
    overrides = {
        ov.product_id: ov
        for ov in session.exec(
            select(ProductOverride).where(ProductOverride.product_id.in_(listing_ids))
        )
    }

    by_game: dict[int, list[dict]] = {}
    for product, snap in rows:
        by_game.setdefault(product.game_id, []).append(
            _offer(product, snap, overrides.get(product.id))
        )

    summaries = {}
    for game_id, offers in by_game.items():
        priced = [o for o in offers if o["price"] is not None]
        priced.sort(key=lambda o: o["price"])
        in_stock = [o for o in priced if o["available"]]
        ordered = priced + [o for o in offers if o["price"] is None]
        summaries[game_id] = {
            "game_id": game_id,
            "listing_count": len(offers),
            "store_ids": sorted({o["store_id"] for o in offers}),
            "cheapest": priced[0] if priced else None,
            "cheapest_in_stock": in_stock[0] if in_stock else None,
            "offers": ordered,
            "images": _offer_images(ordered),
        }
    return summaries


def compare_summary(session: Session, game_id: int) -> dict | None:
    """Cross-shop comparison for one game, or None if it has no listings."""
    return _compare_summaries(session, {game_id}).get(game_id)


def _price_histories(session: Session, product_ids: set[int]) -> dict[int, list[dict]]:
    """Last 12 readings per listing, newest first.

    Timestamps ride along so a card can say how long its price has stood.
    """
    if not product_ids:
        return {}
    rn_col = (
        func.row_number()
        .over(
            partition_by=PriceSnapshot.product_id,
            order_by=PriceSnapshot.recorded_at.desc(),
        )
        .label("rn")
    )
    subq = (
        select(
            PriceSnapshot.product_id,
            PriceSnapshot.price,
            PriceSnapshot.recorded_at,
            rn_col,
        )
        .where(PriceSnapshot.product_id.in_(product_ids))
        .subquery()
    )
    histories: dict[int, list[dict]] = {}
    for pid, price, recorded_at in session.exec(
        select(subq.c.product_id, subq.c.price, subq.c.recorded_at)
        .where(subq.c.rn <= 12)
        .order_by(subq.c.product_id, subq.c.rn)
    ):
        histories.setdefault(int(pid), []).append(
            {"price": float(price), "recorded_at": recorded_at}
        )
    return histories


def make_cards(
    session: Session,
    items: list[CatalogRow],
    *,
    extra: dict[int, dict] | None = None,
) -> list[dict]:
    """Batch-enrich (listing, latest snapshot, game) rows into card dicts."""
    product_ids = [p.id for p, _, _ in items if p.id is not None]
    game_ids = {g.id for _, _, g in items if g.id is not None}
    bgg_ids = {g.bgg_id for _, _, g in items if g.bgg_id}

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

    # The watch rides on every card so a target can be set wherever the game
    # shows up, not only on the watchlist page.
    watches: dict[int, WatchlistItem] = {}
    if game_ids:
        for w in session.exec(
            select(WatchlistItem).where(
                WatchlistItem.game_id.in_(game_ids), WatchlistItem.active
            )
        ):
            watches[w.game_id] = w

    compares = _compare_summaries(session, game_ids)

    # Sibling listings are included so a multi-shop card can graph the offer it
    # quotes, not just its own listing.
    wanted = set(product_ids)
    for summary in compares.values():
        wanted.update(o["product_id"] for o in summary["offers"])
    histories = _price_histories(session, wanted)
    for summary in compares.values():
        for offer in summary["offers"]:
            offer["price_history"] = histories.get(offer["product_id"], [])

    cards = []
    for product, snap, game in items:
        price = snap.price if snap else None
        cap = snap.compare_at_price if snap else None
        compare = compares.get(game.id)
        card = {
            "product": product,
            "game": game,
            "latest_price": snap,
            "bgg": _parse_bgg(bgg_cache.get(game.bgg_id), game.bgg_id),
            "override": overrides.get(product.id) if product.id else None,
            "discount_pct": _discount_pct(price, cap),
            "price_history": histories.get(product.id, []),
            # Only when more than one shop sells it — otherwise there is nothing
            # to compare and every card would carry a redundant payload.
            "compare": compare if compare and compare["listing_count"] > 1 else None,
            "watchlist": watches.get(game.id),
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
) -> list[CatalogRow]:
    """Filtered, sorted, paginated catalog rows, one per game.

    A merged game keeps every listing row in the join, so duplicates are
    collapsed per page (same approach as hidden_games/search): a merged
    game whose listings straddle a page boundary can make that page come
    back short of `limit`.
    """
    latest, bgg, first_seen, prev_snap, watchlist, store_count = _subqueries()
    registry = build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
        store_count_subq=store_count,
    )
    stmt = _build_joined_stmt(
        latest, bgg, first_seen, prev_snap, watchlist, store_count
    )

    filter_on_hidden = filter_node is not None and filter_uses_field(
        filter_node, "hidden"
    )
    if not include_hidden and not filter_on_hidden:
        stmt = stmt.where(Game.hidden == False)  # noqa: E712

    if filter_node is not None:
        stmt = stmt.where(apply_filter(filter_node, registry))

    if sorts:
        stmt = apply_sorts(stmt, sorts, registry)
    else:
        stmt = stmt.order_by(Game.title.asc())

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()

    seen: set[int] = set()
    unique: list[CatalogRow] = []
    for product, snap, game in rows:
        if game.id in seen:
            continue
        seen.add(game.id)
        unique.append((product, snap, game))
    return unique


def count_products(
    session: Session,
    *,
    filter_node: FilterNode | None = None,
    include_hidden: bool = False,
) -> int:
    """Total matching game count (for pagination) — distinct, to match query_products."""
    latest, bgg, first_seen, prev_snap, watchlist, store_count = _subqueries()
    registry = build_field_registry(
        bgg_subq=bgg,
        first_seen_subq=first_seen,
        prev_snap_subq=prev_snap,
        watchlist_subq=watchlist,
        store_count_subq=store_count,
    )
    stmt = (
        select(func.count(func.distinct(Game.id)))
        .select_from(Product)
        .join(Game, Product.game_id == Game.id)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .join(bgg, Game.bgg_id == bgg.c.bgg_id, isouter=True)
        .join(first_seen, Product.id == first_seen.c.product_id, isouter=True)
        .join(prev_snap, Product.id == prev_snap.c.product_id, isouter=True)
        .join(watchlist, Product.game_id == watchlist.c.game_id, isouter=True)
        .join(store_count, Product.game_id == store_count.c.game_id, isouter=True)
    )
    filter_on_hidden = filter_node is not None and filter_uses_field(
        filter_node, "hidden"
    )
    if not include_hidden and not filter_on_hidden:
        stmt = stmt.where(Game.hidden == False)  # noqa: E712
    if filter_node is not None:
        stmt = stmt.where(apply_filter(filter_node, registry))
    return session.exec(stmt).one()


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def _ranked_snapshots_subq():
    """Each snapshot with recency rank (1 = latest) per listing."""
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
    """Listings whose latest price is below their previous recorded price."""
    ranked = _ranked_snapshots_subq()
    latest = select(ranked).where(ranked.c.rn == 1).subquery()
    prev = select(ranked).where(ranked.c.rn == 2).subquery()
    drop_pct = (prev.c.price - latest.c.price) / prev.c.price
    stmt = (
        select(Product, PriceSnapshot, Game, prev.c.price.label("previous_price"))
        .join(Game, Product.game_id == Game.id)
        .join(latest, Product.id == latest.c.product_id)
        .join(prev, Product.id == prev.c.product_id)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == Product.id)
            & (PriceSnapshot.recorded_at == latest.c.recorded_at),
        )
        .where(latest.c.price < prev.c.price)
        .where(Game.hidden == False)  # noqa: E712
    )
    if in_stock_only:
        stmt = stmt.where(latest.c.available == True)  # noqa: E712
    stmt = stmt.order_by(drop_pct.desc())
    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    extra = {r[0].id: {"previous_price": r[3]} for r in rows}
    return make_cards(session, [(r[0], r[1], r[2]) for r in rows], extra=extra)


def new_additions(session: Session, *, page: int = 1, limit: int = 12) -> list[dict]:
    """Most recently first-seen listings."""
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


def _rows_by_ids(session: Session, ids: list[int]) -> list[CatalogRow]:
    """Catalog rows for the given listing ids, in the given order."""
    if not ids:
        return []
    latest, bgg, first_seen, prev_snap, watchlist, store_count = _subqueries()
    stmt = _build_joined_stmt(
        latest, bgg, first_seen, prev_snap, watchlist, store_count
    ).where(Product.id.in_(ids))
    by_id = {r[0].id: (r[0], r[1], r[2]) for r in session.exec(stmt).all()}
    return [by_id[i] for i in ids if i in by_id]


def cards_by_ids(session: Session, ids: list[int]) -> list[dict]:
    """Enriched cards for the given listing ids, in the given order."""
    return make_cards(session, _rows_by_ids(session, ids))


def search(session: Session, *, q: str, limit: int = 24) -> list[dict]:
    """Name search for the global search bar.

    Ranked and typo-tolerant: scoring runs in Python over the candidate names
    because SQLite `LIKE` can only do substrings, which makes a single typo
    return nothing at all. See app.text_search.

    One listing per game, so a merged game appears once.
    """
    if not q or not q.strip():
        return []
    candidates = session.exec(
        select(Product.id, Game.title, Product.game_id)
        .join(Game, Product.game_id == Game.id)
        .where(Game.hidden == False)  # noqa: E712
    ).all()

    seen_games: set[int] = set()
    deduped: list[tuple[int, str]] = []
    for product_id, title, game_id in candidates:
        if game_id in seen_games:
            continue
        seen_games.add(game_id)
        deduped.append((product_id, title))

    ranked = rank_titles(q, deduped, limit=limit)
    return cards_by_ids(session, [pid for pid, _ in ranked])


def hidden_games(session: Session, *, page: int = 1, limit: int = 48) -> list[dict]:
    """Enriched cards for hidden games, one listing each."""
    latest = _latest_snapshot_subq()
    stmt = (
        select(Product, PriceSnapshot, Game)
        .join(Game, Product.game_id == Game.id)
        .join(latest, Product.id == latest.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest.c.product_id)
            & (PriceSnapshot.recorded_at == latest.c.max_date),
            isouter=True,
        )
        .where(Game.hidden == True)  # noqa: E712
        .order_by(Product.updated_at.desc())
    )
    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()

    seen: set[int] = set()
    unique: list[CatalogRow] = []
    for product, snap, game in rows:
        if game.id in seen:
            continue
        seen.add(game.id)
        unique.append((product, snap, game))
    return make_cards(session, unique)


def enabled_stores(session: Session) -> list[Store]:
    return session.exec(select(Store).where(Store.enabled)).all()
