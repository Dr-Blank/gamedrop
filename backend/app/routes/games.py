"""Game endpoints: the compare view, renaming, hiding, and the merge queue."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..logger import get_logger
from ..models import Game, Product
from ..services import games as service

router = APIRouter(prefix="/games", tags=["games"])
log = get_logger(__name__)


class GamePatch(BaseModel):
    title: str | None = None
    bgg_id: int | None = None
    note: str | None = None
    hidden: bool | None = None


# Declared before /{game_id} so the literal path isn't swallowed by it.
@router.get("/suggestions")
def merge_queue(limit: int = 20, session: Session = Depends(get_session)):
    """Catalog-wide merge candidates for bulk review."""
    return {"items": service.suggestion_queue(session, limit=limit)}


@router.get("/for-listing/{product_id}")
def game_for_listing(product_id: int, session: Session = Depends(get_session)):
    """Which game a listing belongs to — lets an old listing URL resolve."""
    listing = session.get(Product, product_id)
    if listing is None:
        raise HTTPException(404, "Product not found")
    return {"game_id": listing.game_id, "store_id": listing.store_id}


@router.get("/{game_id}")
def get_game(game_id: int, session: Session = Depends(get_session)):
    try:
        return service.game_payload(session, game_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/{game_id}")
def update_game(
    game_id: int,
    body: GamePatch,
    session: Session = Depends(get_session),
):
    """Rename a game, set its BGG link, note, or hide it."""
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "Game not found")

    fields = body.model_dump(exclude_unset=True)
    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise HTTPException(400, "title must not be blank")
        game.title = title
    if "note" in fields:
        note = (fields["note"] or "").strip()
        game.note = note or None
    if "hidden" in fields:
        game.hidden = bool(fields["hidden"])
    if "bgg_id" in fields:
        game.bgg_id = fields["bgg_id"]

    session.add(game)
    session.commit()
    log.info("game %s updated: %s", game_id, ", ".join(fields) or "nothing")
    return service.game_payload(session, game_id)


@router.get("/{game_id}/listing/{product_id}")
def listing_detail(
    game_id: int,
    product_id: int,
    limit: int = 90,
    session: Session = Depends(get_session),
):
    """One shop's price history for this game."""
    from sqlmodel import desc, select

    from ..models import PriceSnapshot, ProductOverride

    listing = session.get(Product, product_id)
    if listing is None or listing.game_id != game_id:
        raise HTTPException(404, "Listing not found for this game")
    snapshots = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(desc(PriceSnapshot.recorded_at))
        .limit(limit)
    ).all()
    return {
        "product": listing,
        "history": snapshots,
        "override": session.get(ProductOverride, product_id),
        "updated_at": datetime.utcnow(),
    }
