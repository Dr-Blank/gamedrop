from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, desc, select

from ..db import get_session
from ..logger import get_logger
from ..models import Game, PriceSnapshot, Product, ProductOverride, WatchlistItem
from ..snapshots import MANUAL, effective, split_ignored
from ..text_search import rank_titles

router = APIRouter(prefix="/prices", tags=["prices"])
log = get_logger(__name__)


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
    ).all()
    kept, ignored = split_ignored(list(snapshots))
    watchlist_item = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == product.game_id,
            WatchlistItem.active == True,  # noqa: E712
        )
    ).first()
    return {
        "product": product,
        "game": session.get(Game, product.game_id),
        "history": kept[:limit],
        "ignored": ignored,
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
            .where(PriceSnapshot.product_id == p.id, effective())
            .order_by(desc(PriceSnapshot.recorded_at))
            .limit(1)
        ).first()
        results.append({"product": p, "latest_price": latest})

    return results


def _set_ignored(snapshot_id: int, value: bool, session: Session) -> PriceSnapshot:
    snap = session.get(PriceSnapshot, snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    snap.ignored = value
    session.add(snap)
    session.commit()
    session.refresh(snap)
    log.info(
        "snapshot %s %s",
        snapshot_id,
        "ignored" if value else "restored",
        extra={"product_id": snap.product_id},
    )
    return snap


@router.put("/snapshot/{snapshot_id}/ignore")
def ignore_snapshot(snapshot_id: int, session: Session = Depends(get_session)):
    """Drop a reading out of charts, stats, filters and alerts without losing it."""
    return _set_ignored(snapshot_id, True, session)


@router.delete("/snapshot/{snapshot_id}/ignore")
def restore_snapshot(snapshot_id: int, session: Session = Depends(get_session)):
    return _set_ignored(snapshot_id, False, session)


class ManualSnapshot(BaseModel):
    price: float
    recorded_at: datetime
    available: bool = True
    compare_at_price: float | None = None


@router.post("/product/{product_id}/snapshot")
def add_manual_snapshot(
    product_id: int,
    body: ManualSnapshot,
    session: Session = Depends(get_session),
):
    """Record a price the scraper never saw — a listing's history from before tracking."""
    if not session.get(Product, product_id):
        raise HTTPException(404, "Product not found")
    if body.price < 0:
        raise HTTPException(400, "Price cannot be negative")

    snap = PriceSnapshot(
        product_id=product_id,
        price=body.price,
        compare_at_price=body.compare_at_price,
        available=body.available,
        recorded_at=body.recorded_at,
        source=MANUAL,
    )
    session.add(snap)
    session.commit()
    session.refresh(snap)
    log.info(
        "manual snapshot added: product %s at %s",
        product_id,
        body.recorded_at,
        extra={"product_id": product_id},
    )
    return snap


@router.delete("/snapshot/{snapshot_id}")
def delete_manual_snapshot(snapshot_id: int, session: Session = Depends(get_session)):
    """Only hand-entered readings are deletable — a scraped one is what the shop said."""
    snap = session.get(PriceSnapshot, snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    if snap.source != MANUAL:
        raise HTTPException(400, "Only manual snapshots can be deleted; ignore instead")
    session.delete(snap)
    session.commit()
    log.info(
        "manual snapshot %s deleted",
        snapshot_id,
        extra={"product_id": snap.product_id},
    )
    return {"ok": True}
