from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session, select

from ..db import get_session
from ..logger import get_logger
from ..models import Game, Product, WatchlistItem
from ..repositories import watchlist as wl_repo

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
log = get_logger(__name__)


class WatchlistAdd(BaseModel):
    """Watching is a decision about the game. A listing id is accepted too and
    resolved to its game, so a card only needs to know what it is showing."""

    game_id: int | None = None
    product_id: int | None = None
    target_price: float | None = None
    notify_price_drop: bool = True
    notify_back_in_stock: bool = True
    notify_target_reached: bool = True

    @model_validator(mode="after")
    def require_a_target(self):
        if self.game_id is None and self.product_id is None:
            raise ValueError("game_id or product_id is required")
        return self


class WatchlistPatch(BaseModel):
    target_price: float | None = None
    notify_price_drop: bool | None = None
    notify_back_in_stock: bool | None = None
    notify_target_reached: bool | None = None
    notify_price_increase: bool | None = None
    notify_out_of_stock: bool | None = None


def _resolve_game_id(body: WatchlistAdd, session: Session) -> int:
    if body.game_id is not None:
        if session.get(Game, body.game_id) is None:
            raise HTTPException(404, "Game not found")
        return body.game_id
    listing = session.get(Product, body.product_id)
    if listing is None:
        raise HTTPException(404, "Product not found")
    return listing.game_id


@router.get("/")
def list_watchlist(session: Session = Depends(get_session)):
    """The watches themselves. Cards for them come from a browse query."""
    return wl_repo.active_items(session)


@router.post("/")
def add_to_watchlist(body: WatchlistAdd, session: Session = Depends(get_session)):
    game_id = _resolve_game_id(body, session)

    existing = session.exec(
        select(WatchlistItem).where(WatchlistItem.game_id == game_id)
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
        log.info("watchlist reactivated: game %s", game_id)
        return existing

    item = WatchlistItem(
        game_id=game_id,
        target_price=body.target_price,
        notify_price_drop=body.notify_price_drop,
        notify_back_in_stock=body.notify_back_in_stock,
        notify_target_reached=body.notify_target_reached,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    log.info("watchlist added: game %s", game_id)
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
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, field, value)
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
    log.info("watchlist removed: item %s (game %s)", item_id, item.game_id)
    return {"ok": True}
