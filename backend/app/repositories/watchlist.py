"""Watchlist data-access. Reuses catalog card enrichment so a watched game
renders with the same shape (bgg, compare, discount) as anywhere else."""

from __future__ import annotations

from sqlmodel import Session, desc, select

from ..models import Game, PriceSnapshot, Product, Store, WatchlistItem
from . import catalog


def active_items(session: Session) -> list[WatchlistItem]:
    return session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()


def cards(session: Session, *, limit: int | None = None) -> list[dict]:
    """Active watchlist as enriched cards, each carrying `watchlist` + `store`.

    The card shows the cheapest buyable listing of the game, so a watched game
    appears once however many shops sell it.
    """
    items = active_items(session)
    if limit is not None:
        items = items[:limit]

    rows: list[catalog.CatalogRow] = []
    meta: dict[int, dict] = {}
    for item in items:
        game = session.get(Game, item.game_id)
        if game is None:
            continue
        summary = catalog.compare_summary(session, item.game_id)
        if not summary or not summary["offers"]:
            continue
        best = (
            summary["cheapest_in_stock"] or summary["cheapest"] or summary["offers"][0]
        )
        product = session.get(Product, best["product_id"])
        if product is None:
            continue
        rows.append((product, _latest(session, product.id), game))
        meta[product.id] = {
            "watchlist": item,
            "store": session.get(Store, product.store_id),
        }

    return catalog.make_cards(session, rows, extra=meta)


def _latest(session: Session, product_id: int) -> PriceSnapshot | None:
    return session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.recorded_at))
        .limit(1)
    ).first()
