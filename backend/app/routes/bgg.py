from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..bgg_client import get_game, search_games
from ..db import get_session
from ..models import Product

router = APIRouter(prefix="/bgg", tags=["bgg"])


@router.get("/search")
async def bgg_search(q: str):
    if not q or len(q) < 2:
        raise HTTPException(400, "Query too short")
    return await search_games(q)


@router.get("/game/{bgg_id}")
async def bgg_game(bgg_id: int):
    return await get_game(bgg_id)


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
