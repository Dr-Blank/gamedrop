from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, desc, select

from ..db import get_session
from ..models import Game, PriceSnapshot, Product, ProductOverride, WatchlistItem
from ..text_search import rank_titles

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/product/{product_id}")
def price_history(
    product_id: int,
    limit: int = 90,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    snapshots = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.recorded_at))
        .limit(limit)
    ).all()
    watchlist_item = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == product.game_id,
            WatchlistItem.active == True,  # noqa: E712
        )
    ).first()
    return {
        "product": product,
        "game": session.get(Game, product.game_id),
        "history": snapshots,
        "override": session.get(ProductOverride, product_id),
        "watchlist_item": watchlist_item,
    }


@router.get("/search")
def search_by_name(
    q: str,
    store_id: str | None = None,
    session: Session = Depends(get_session),
):
    """Search listings by game name, return with latest price snapshot."""
    query = select(Product, Game).join(Game, Product.game_id == Game.id)
    if store_id:
        query = query.where(Product.store_id == store_id)
    rows = session.exec(query).all()
    by_id = {p.id: p for p, _ in rows}
    ranked = rank_titles(q, [(p.id, g.title) for p, g in rows])
    matched = [by_id[pid] for pid, _ in ranked]

    results = []
    for p in matched:
        latest = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == p.id)
            .order_by(desc(PriceSnapshot.recorded_at))
            .limit(1)
        ).first()
        results.append({"product": p, "latest_price": latest})

    return results
