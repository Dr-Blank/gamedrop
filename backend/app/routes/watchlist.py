from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..logger import get_logger
from ..models import Product, WatchlistItem
from ..repositories import watchlist as wl_repo

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
log = get_logger(__name__)


class WatchlistAdd(BaseModel):
    product_id: int
    target_price: float | None = None
    notify_price_drop: bool = True
    notify_back_in_stock: bool = True
    notify_target_reached: bool = True


class WatchlistPatch(BaseModel):
    target_price: float | None = None
    notify_price_drop: bool | None = None
    notify_back_in_stock: bool | None = None
    notify_target_reached: bool | None = None
    product_id: int | None = None  # keep for backward compat


@router.get("/")
def list_watchlist(session: Session = Depends(get_session)):
    return wl_repo.cards(session)


@router.post("/")
def add_to_watchlist(body: WatchlistAdd, session: Session = Depends(get_session)):
    product = session.get(Product, body.product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    existing = session.exec(
        select(WatchlistItem).where(WatchlistItem.product_id == body.product_id)
    ).first()
    if existing:
        existing.target_price = body.target_price
        existing.active = True
        existing.notify_price_drop = body.notify_price_drop
        existing.notify_back_in_stock = body.notify_back_in_stock
        existing.notify_target_reached = body.notify_target_reached
        session.add(existing)
        session.commit()
        session.refresh(existing)
        log.info(
            "watchlist reactivated: product %s",
            body.product_id,
            extra={"product_id": body.product_id},
        )
        return existing

    item = WatchlistItem(
        product_id=body.product_id,
        target_price=body.target_price,
        notify_price_drop=body.notify_price_drop,
        notify_back_in_stock=body.notify_back_in_stock,
        notify_target_reached=body.notify_target_reached,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    log.info(
        "watchlist added: product %s",
        body.product_id,
        extra={"product_id": body.product_id},
    )
    return item


@router.patch("/{item_id}")
def update_watchlist(
    item_id: int,
    body: WatchlistPatch,
    session: Session = Depends(get_session),
):
    item = session.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    if body.target_price is not None:
        item.target_price = body.target_price
    if body.notify_price_drop is not None:
        item.notify_price_drop = body.notify_price_drop
    if body.notify_back_in_stock is not None:
        item.notify_back_in_stock = body.notify_back_in_stock
    if body.notify_target_reached is not None:
        item.notify_target_reached = body.notify_target_reached
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}")
def remove_from_watchlist(item_id: int, session: Session = Depends(get_session)):
    item = session.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.active = False
    session.add(item)
    session.commit()
    log.info(
        "watchlist removed: item %s (product %s)",
        item_id,
        item.product_id,
        extra={"product_id": item.product_id},
    )
    return {"ok": True}
