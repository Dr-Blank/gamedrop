from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, desc

from ..db import get_session
from ..models import PriceSnapshot, Product

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
    return {"product": product, "history": snapshots}


@router.get("/search")
def search_by_name(
    q: str,
    store_id: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Search products by name, return with latest price snapshot."""
    query = select(Product)
    if store_id:
        query = query.where(Product.store_id == store_id)
    products = session.exec(query).all()
    ql = q.lower()
    matched = [p for p in products if ql in p.title.lower()]

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
