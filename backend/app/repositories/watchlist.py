"""Watchlist data-access. Reuses catalog card enrichment so a watchlist entry
renders with the same shape (bgg, override, discount) as anywhere else."""

from __future__ import annotations

from sqlmodel import Session, desc, select

from ..models import PriceSnapshot, Product, Store, WatchlistItem
from . import catalog


def _latest(session: Session, product_id: int) -> PriceSnapshot | None:
    return session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.recorded_at))
        .limit(1)
    ).first()


def active_items(session: Session) -> list[WatchlistItem]:
    return session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()


def cards(session: Session, *, limit: int | None = None) -> list[dict]:
    """Active watchlist as enriched cards, each carrying `watchlist` + `store`."""
    items = active_items(session)
    if limit is not None:
        items = items[:limit]

    pairs: list[tuple[Product, PriceSnapshot | None]] = []
    meta: dict[int, dict] = {}
    for item in items:
        product = session.get(Product, item.product_id)
        if not product:
            continue
        pairs.append((product, _latest(session, item.product_id)))
        meta[product.id] = {
            "watchlist": item,
            "store": session.get(Store, product.store_id),
        }

    return catalog.make_cards(session, pairs, extra=meta)
