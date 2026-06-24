import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, or_
from sqlmodel import Session, select

from ..bgg_client import get_game, search_games
from ..db import get_session
from ..models import Product, ProductOverride, WatchlistItem

router = APIRouter(prefix="/bgg", tags=["bgg"])

_STRIP_RE = re.compile(r"\s*[-–|:]\s+.*$")


def _clean_query(q: str) -> str:
    """Strip Shopify marketing suffixes and cap length for BGG search."""
    q = _STRIP_RE.sub("", q.strip())
    return q[:60].strip()


@router.get("/search")
async def bgg_search(q: str):
    if not q or len(q) < 2:
        raise HTTPException(400, "Query too short")
    cleaned = _clean_query(q)
    if len(cleaned) < 2:
        raise HTTPException(400, "Query too short after cleaning")
    return await search_games(cleaned)


@router.get("/game/{bgg_id}")
async def bgg_game(bgg_id: int):
    return await get_game(bgg_id)


@router.post("/game/{bgg_id}/refresh")
async def refresh_bgg_cache(bgg_id: int):
    return await get_game(bgg_id, force=True)


@router.get("/unlinked")
def get_unlinked_products(
    page: int = 1,
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """Products with no bgg_id. Watchlisted items sort first."""
    base_where = [
        Product.bgg_id.is_(None),
        or_(
            ProductOverride.product_id.is_(None),
            ProductOverride.bgg_id.is_(None),
        ),
        Product.hidden == False,  # noqa: E712
    ]
    watched = case(
        (WatchlistItem.product_id.isnot(None), 0),
        else_=1,
    )
    stmt = (
        select(Product, WatchlistItem.product_id.label("watched"))
        .outerjoin(ProductOverride, Product.id == ProductOverride.product_id)
        .outerjoin(WatchlistItem, Product.id == WatchlistItem.product_id)
        .where(*base_where)
        .order_by(watched, Product.title)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    count_stmt = (
        select(func.count())
        .select_from(Product)
        .outerjoin(ProductOverride, Product.id == ProductOverride.product_id)
        .where(*base_where)
    )
    rows = session.exec(stmt).all()
    total = session.exec(count_stmt).one()
    return {
        "products": [
            {
                "id": p.id,
                "title": p.title,
                "image_url": p.image_url,
                "watched": w is not None,
            }
            for p, w in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/link/{product_id}")
def unlink_bgg(
    product_id: int,
    session: Session = Depends(get_session),
):
    """Clear BGG link from product and its override (if set)."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.bgg_id = None
    product.updated_at = __import__("datetime").datetime.utcnow()
    ov = session.get(ProductOverride, product_id)
    if ov and ov.bgg_id is not None:
        ov.bgg_id = None
        ov.updated_at = __import__("datetime").datetime.utcnow()
        session.add(ov)
    session.add(product)
    session.commit()
    return {"ok": True}


@router.post("/game/{bgg_id}/link/{product_id}")
def link_game_to_product(
    bgg_id: int,
    product_id: int,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.bgg_id = bgg_id
    product.updated_at = __import__("datetime").datetime.utcnow()
    session.add(product)
    session.commit()
    return {"ok": True}
