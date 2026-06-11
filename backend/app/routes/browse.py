import json

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import BggCache, PriceSnapshot, Product, Store

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/")
def browse(
    q: str | None = None,
    store_id: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
    has_bgg: bool | None = None,
    sort: str = "title",  # title | price_asc | price_desc
    page: int = 1,
    limit: int = 48,
    session: Session = Depends(get_session),
):
    latest_subq = (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )

    stmt = (
        select(Product, PriceSnapshot)
        .join(latest_subq, Product.id == latest_subq.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest_subq.c.product_id)
            & (PriceSnapshot.recorded_at == latest_subq.c.max_date),
            isouter=True,
        )
    )

    if q:
        stmt = stmt.where(Product.title.ilike(f"%{q}%"))
    if store_id:
        stmt = stmt.where(Product.store_id == store_id)
    if in_stock is not None:
        stmt = stmt.where(PriceSnapshot.available == in_stock)
    if has_bgg is True:
        stmt = stmt.where(Product.bgg_id.is_not(None))
    if has_bgg is False:
        stmt = stmt.where(Product.bgg_id.is_(None))
    if min_price is not None:
        stmt = stmt.where(PriceSnapshot.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(PriceSnapshot.price <= max_price)

    if sort == "price_asc":
        stmt = stmt.order_by(PriceSnapshot.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(PriceSnapshot.price.desc())
    else:
        stmt = stmt.order_by(Product.title.asc())

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()

    results = []
    for product, snap in rows:
        bgg_data = None
        if product.bgg_id:
            cached = session.get(BggCache, product.bgg_id)
            if cached:
                try:
                    parsed = json.loads(cached.data)
                    bgg_data = {
                        "bgg_id": product.bgg_id,
                        "name": parsed.get("name"),
                        "avg_rating": parsed.get("avg_rating"),
                        "bgg_rating": parsed.get("bgg_rating"),
                        "rank": parsed.get("rank"),
                        "avg_weight": parsed.get("avg_weight"),
                        "thumbnail": parsed.get("thumbnail"),
                        "bgg_url": parsed.get("bgg_url"),
                    }
                except (json.JSONDecodeError, TypeError):
                    pass
        results.append({"product": product, "latest_price": snap, "bgg": bgg_data})

    return {"items": results, "page": page, "limit": limit}


@router.get("/stores")
def browse_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store).where(Store.enabled)).all()
