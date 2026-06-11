from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, desc, select

from ..db import get_session
from ..models import PriceSnapshot, Product, Store, WatchlistItem

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    product_id: int
    target_price: float | None = None


@router.get("/")
def list_watchlist(session: Session = Depends(get_session)):
    items = session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()
    result = []
    for item in items:
        product = session.get(Product, item.product_id)
        if not product:
            continue
        store = session.get(Store, product.store_id)
        latest = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == item.product_id)
            .order_by(desc(PriceSnapshot.recorded_at))
            .limit(1)
        ).first()
        result.append(
            {
                "watchlist": item,
                "product": product,
                "store": store,
                "latest_price": latest,
            }
        )
    return result


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
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    item = WatchlistItem(product_id=body.product_id, target_price=body.target_price)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/{item_id}")
def update_watchlist(
    item_id: int,
    body: WatchlistAdd,
    session: Session = Depends(get_session),
):
    item = session.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.target_price = body.target_price
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
    return {"ok": True}
