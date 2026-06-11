import json
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlmodel import Session, select

from ..db import get_session
from ..models import BggCache, PriceSnapshot, Product, Store

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/")
def browse(
    q: Optional[str] = None,
    store_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    has_bgg: Optional[bool] = None,
    min_bgg_rating: Optional[float] = None,
    sort: str = "title",        # title | price_asc | price_desc | bgg_rating
    page: int = 1,
    limit: int = 48,
    session: Session = Depends(get_session),
):
    # Latest snapshot per product via correlated subquery
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

    # Apply sort before pagination
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

        # Filter by BGG rating after fetching (SQLite can't query JSON inline)
        if min_bgg_rating and bgg_data:
            try:
                if float(bgg_data.get("avg_rating") or 0) < min_bgg_rating:
                    continue
            except (TypeError, ValueError):
                continue
        elif min_bgg_rating and not bgg_data:
            continue

        results.append({
            "product": product,
            "latest_price": snap,
            "bgg": bgg_data,
        })

    return {"items": results, "page": page, "limit": limit}


@router.get("/stores")
def browse_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store).where(Store.enabled == True)).all()
