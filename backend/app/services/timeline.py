"""Every price and stock change across shops, newest first."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, or_
from sqlmodel import Session, select

from ..models import Game, PriceSnapshot, Product, WatchlistItem
from ..snapshots import effective

KINDS = ("drop", "rise", "restock", "oos", "listed")
#: How far back each game's chart reaches before its oldest event on the page.
CHART_LEAD = timedelta(days=30)


def encode_cursor(at: datetime, snapshot_id: int) -> str:
    return f"{at.isoformat()}|{snapshot_id}"


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    at, _, sid = cursor.rpartition("|")
    try:
        return datetime.fromisoformat(at), int(sid)
    except ValueError as e:
        raise ValueError(f"Bad cursor: {cursor!r}") from e


def _ranked(upto: datetime | None, listings):
    """Each counted reading beside the one before it on the same variant.

    Bounds go inside the window: SQLite won't push an outer WHERE through it.
    """

    def prior(col):
        return func.lag(col).over(
            partition_by=(PriceSnapshot.product_id, PriceSnapshot.variant_id),
            order_by=(PriceSnapshot.recorded_at.asc(), PriceSnapshot.id.asc()),
        )

    # Lag only looks back, so a later cut-off and whole listings are safe to drop.
    clauses = [effective()]
    if upto is not None:
        clauses.append(PriceSnapshot.recorded_at <= upto)
    if listings is not None:
        clauses.append(PriceSnapshot.product_id.in_(listings))
    return (
        select(
            PriceSnapshot.id.label("id"),
            PriceSnapshot.product_id.label("product_id"),
            PriceSnapshot.variant_title.label("variant_title"),
            PriceSnapshot.recorded_at.label("recorded_at"),
            PriceSnapshot.price.label("price"),
            PriceSnapshot.available.label("available"),
            PriceSnapshot.source.label("source"),
            prior(PriceSnapshot.id).label("prev_id"),
            prior(PriceSnapshot.price).label("prev_price"),
            prior(PriceSnapshot.available).label("prev_available"),
        )
        .where(*clauses)
        .subquery()
    )


def change_events(
    session: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    store_ids: list[str] | None = None,
    kinds: list[str] | None = None,
    min_pct: float | None = None,
    watchlist: bool = False,
    include_hidden: bool = False,
    before: str | None = None,
    limit: int = 100,
) -> dict:
    """One page of change events plus the per-shop history to chart them."""
    cursor = decode_cursor(before) if before else None
    upto = min(
        (t for t in (until, cursor and cursor[0]) if t is not None), default=None
    )
    listings = None
    if store_ids or watchlist:
        listings = select(Product.id)
        if store_ids:
            listings = listings.where(Product.store_id.in_(store_ids))
        if watchlist:
            watched = select(WatchlistItem.game_id).where(WatchlistItem.active == True)  # noqa: E712
            listings = listings.where(Product.game_id.in_(watched))
    r = _ranked(upto, listings)
    # A price move outranks a stock flip landing on the same reading.
    kind = case(
        (r.c.prev_id.is_(None), "listed"),
        (r.c.price < r.c.prev_price, "drop"),
        (r.c.price > r.c.prev_price, "rise"),
        (and_(r.c.available, ~r.c.prev_available), "restock"),
        (and_(~r.c.available, r.c.prev_available), "oos"),
        else_=None,
    ).label("kind")

    clauses = [kind.is_not(None)]
    if not include_hidden:
        clauses.append(Game.hidden == False)  # noqa: E712
    if since is not None:
        clauses.append(r.c.recorded_at >= since)
    if until is not None:
        clauses.append(r.c.recorded_at <= until)
    if kinds:
        clauses.append(kind.in_(kinds))
    if min_pct:
        # Only a price move has a size; stock events pass through.
        moved_pct = func.abs(r.c.price - r.c.prev_price) * 100.0 / r.c.prev_price
        clauses.append(
            or_(
                kind.not_in(("drop", "rise")), r.c.prev_price == 0, moved_pct >= min_pct
            )
        )
    if cursor:
        at, sid = cursor
        clauses.append(
            or_(r.c.recorded_at < at, and_(r.c.recorded_at == at, r.c.id < sid))
        )

    rows = session.exec(
        select(r, kind, Product.store_id, Product.game_id, Product.title, Game.title)
        .join(Product, Product.id == r.c.product_id)
        .join(Game, Game.id == Product.game_id)
        .where(*clauses)
        .order_by(r.c.recorded_at.desc(), r.c.id.desc())
        .limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]

    events = [
        {
            "snapshot_id": row.id,
            "product_id": row.product_id,
            "game_id": row.game_id,
            "store_id": row.store_id,
            "variant_title": row.variant_title,
            "kind": row.kind,
            "at": row.recorded_at,
            "price": row.price,
            "prev_price": row.prev_price,
            "available": row.available,
            "prev_available": row.prev_available,
            "source": row.source,
        }
        for row in rows
    ]
    next_cursor = (
        encode_cursor(rows[-1].recorded_at, rows[-1].id) if more and rows else None
    )
    return {
        "events": events,
        "games": _games(session, events),
        "next_cursor": next_cursor,
    }


def _games(session: Session, events: list[dict]) -> dict[int, dict]:
    """Title, image and every shop's recent history for each game on the page."""
    if not events:
        return {}
    game_ids = sorted({e["game_id"] for e in events})
    chart_from = min(e["at"] for e in events) - CHART_LEAD
    listings = session.exec(select(Product).where(Product.game_id.in_(game_ids))).all()
    games = {
        g.id: {
            "game_id": g.id,
            "title": g.title,
            "hidden": g.hidden,
            "image_url": None,
            "series": [],
        }
        for g in session.exec(select(Game).where(Game.id.in_(game_ids))).all()
    }
    for p in listings:
        if p.image_url and not games[p.game_id]["image_url"]:
            games[p.game_id]["image_url"] = p.image_url

    history = _compact_history(session, [p.id for p in listings], chart_from)
    for p in listings:
        if history.get(p.id):
            games[p.game_id]["series"].append(
                {"product_id": p.id, "store_id": p.store_id, "history": history[p.id]}
            )
    return games


def _compact_history(
    session: Session, product_ids: list[int], chart_from: datetime
) -> dict[int, list[dict]]:
    """Turning points since `chart_from`, led by the reading in force at it."""
    if not product_ids:
        return {}
    cols = (
        PriceSnapshot.product_id,
        PriceSnapshot.price,
        PriceSnapshot.available,
        PriceSnapshot.recorded_at,
    )
    mine = (PriceSnapshot.product_id.in_(product_ids), effective())
    last_before = (
        select(
            *cols,
            func.row_number()
            .over(
                partition_by=PriceSnapshot.product_id,
                order_by=(PriceSnapshot.recorded_at.desc(), PriceSnapshot.id.desc()),
            )
            .label("rn"),
        )
        .where(*mine, PriceSnapshot.recorded_at < chart_from)
        .subquery()
    )
    anchors = session.exec(
        select(
            last_before.c.product_id,
            last_before.c.price,
            last_before.c.available,
            last_before.c.recorded_at,
        ).where(last_before.c.rn == 1)
    ).all()
    recent = session.exec(
        select(*cols)
        .where(*mine, PriceSnapshot.recorded_at >= chart_from)
        .order_by(PriceSnapshot.recorded_at.asc(), PriceSnapshot.id.asc())
    ).all()

    by_product: dict[int, list] = {}
    for row in [*anchors, *recent]:
        by_product.setdefault(row.product_id, []).append(row)
    out: dict[int, list[dict]] = {}
    for pid, readings in by_product.items():
        # A standing price scraped daily adds nothing to a step chart.
        kept = [
            r
            for i, r in enumerate(readings)
            if i == 0
            or (r.price, r.available)
            != (readings[i - 1].price, readings[i - 1].available)
        ]
        if readings[-1] is not kept[-1]:
            kept.append(readings[-1])
        out[pid] = [
            {"price": r.price, "available": r.available, "recorded_at": r.recorded_at}
            for r in kept
        ]
    return out
