import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlmodel import Session, select

from ..bgg_client import get_game, search_games
from ..db import get_session
from ..models import Game, Product, WatchlistItem

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
def get_unlinked_games(
    page: int = 1,
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """Games with no BGG link. Watched games sort first."""
    base_where = [
        Game.bgg_id.is_(None),
        Game.hidden == False,  # noqa: E712
    ]
    watched = case((WatchlistItem.game_id.isnot(None), 0), else_=1)
    image = func.min(Product.image_url).label("image_url")
    listing = func.min(Product.id).label("product_id")
    stmt = (
        select(Game, image, listing, WatchlistItem.game_id.label("watched"))
        .join(Product, Product.game_id == Game.id)
        .outerjoin(
            WatchlistItem,
            (WatchlistItem.game_id == Game.id) & (WatchlistItem.active == True),  # noqa: E712
        )
        .where(*base_where)
        .group_by(Game.id)
        .order_by(watched, Game.title)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    count_stmt = (
        select(func.count(func.distinct(Game.id)))
        .select_from(Game)
        .join(Product, Product.game_id == Game.id)
        .where(*base_where)
    )
    rows = session.exec(stmt).all()
    return {
        "games": [
            {
                "id": g.id,
                "product_id": pid,
                "title": g.title,
                "image_url": img,
                "watched": w is not None,
            }
            for g, img, pid, w in rows
        ],
        "total": session.exec(count_stmt).one(),
        "page": page,
        "limit": limit,
    }


def _game_of(product_id: int, session: Session) -> Game:
    """BGG identity belongs to the game, so a listing id resolves to one."""
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    game = session.get(Game, product.game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return game


@router.delete("/link/{product_id}")
def unlink_bgg(product_id: int, session: Session = Depends(get_session)):
    game = _game_of(product_id, session)
    game.bgg_id = None
    session.add(game)
    session.commit()
    return {"ok": True, "game_id": game.id}


@router.post("/game/{bgg_id}/link/{product_id}")
def link_bgg_to_game(
    bgg_id: int,
    product_id: int,
    session: Session = Depends(get_session),
):
    game = _game_of(product_id, session)
    game.bgg_id = bgg_id
    session.add(game)
    session.commit()
    return {"ok": True, "game_id": game.id}
