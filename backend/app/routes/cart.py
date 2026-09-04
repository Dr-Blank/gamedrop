"""Buy queue: what to buy next, from which shop, and what it adds up to."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlmodel import Session

from ..config import get_setting, set_setting
from ..db import get_session
from ..logger import get_logger
from ..models import CartItem, Game, Product
from ..repositories import cart as cart_repo

router = APIRouter(prefix="/cart", tags=["cart"])
log = get_logger(__name__)

BUDGET_KEY = "cart_budget"


class CartAdd(BaseModel):
    """Queuing is a decision about the game; a listing id is accepted too and
    resolved to its game, so a card only needs to know what it is showing."""

    game_id: int | None = None
    product_id: int | None = None
    #: Pins the shop. Omitted, the row follows the cheapest buyable offer.
    pin_store: bool = False
    quantity: int = 1
    priority: str = "normal"
    max_price: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_a_target(self):
        if self.game_id is None and self.product_id is None:
            raise ValueError("game_id or product_id is required")
        return self


class CartPatch(BaseModel):
    product_id: int | None = None
    quantity: int | None = None
    priority: str | None = None
    max_price: float | None = None
    note: str | None = None
    #: Explicit unpin — a null product_id is indistinguishable from "unchanged".
    unpin: bool = False
    clear_max_price: bool = False


class CartReorder(BaseModel):
    ids: list[int]


class BudgetUpdate(BaseModel):
    amount: float | None = None


def _budget() -> float | None:
    raw = get_setting(BUDGET_KEY)
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _resolve(body: CartAdd, session: Session) -> tuple[int, int | None]:
    """(game_id, listing to pin) for an add."""
    if body.product_id is not None:
        listing = session.get(Product, body.product_id)
        if listing is None:
            raise HTTPException(404, "Product not found")
        return listing.game_id, (body.product_id if body.pin_store else None)
    if session.get(Game, body.game_id) is None:
        raise HTTPException(404, "Game not found")
    return body.game_id, None


def _payload(session: Session, items: list[CartItem]) -> dict:
    rows = cart_repo.enrich(session, items)
    budget = _budget()
    return {
        "items": rows,
        "summary": cart_repo.summarise(rows, budget),
        "switches": cart_repo.cheaper_switches(rows),
    }


@router.get("/")
def read_cart(session: Session = Depends(get_session)):
    """The queue in buy order, priced at the shop each row is quoted from."""
    return _payload(session, cart_repo.active_items(session))


@router.get("/purchased")
def read_purchased(session: Session = Depends(get_session)):
    """What has been bought, most recent first."""
    items = cart_repo.purchased_items(session)
    return {"items": cart_repo.enrich(session, items)}


@router.post("/")
def add_to_cart(body: CartAdd, session: Session = Depends(get_session)):
    if body.priority not in cart_repo.PRIORITIES:
        raise HTTPException(422, f"priority must be one of {cart_repo.PRIORITIES}")
    game_id, pinned = _resolve(body, session)

    existing = cart_repo.by_game(session, game_id)
    if existing:
        return existing

    # Recorded on the way in so the row can show what the price has done since.
    from ..repositories import catalog as catalog_repo

    offer = cart_repo.pick_offer(catalog_repo.compare_summary(session, game_id), pinned)

    # A game queued before keeps what was set on it; anything named in this
    # request still wins.
    previous = cart_repo.previous_for_game(session, game_id)
    carried = {
        field: getattr(previous, field)
        for field in cart_repo.CARRIED_FIELDS
        if previous is not None and field not in body.model_fields_set
    }

    position = cart_repo.next_position(session)
    if previous is not None and previous.purchased_at is None:
        item = previous
        item.removed_at = None
    else:
        item = CartItem(game_id=game_id)

    item.product_id = pinned
    item.position = position
    item.added_price = offer["price"] if offer else None
    item.quantity = max(1, carried.get("quantity", body.quantity))
    item.priority = carried.get("priority", body.priority)
    item.max_price = carried.get("max_price", body.max_price)
    item.note = carried.get("note", body.note)

    session.add(item)
    session.commit()
    session.refresh(item)
    log.info("cart added: game %s", game_id)
    return item


@router.patch("/{item_id}")
def update_cart_item(
    item_id: int, body: CartPatch, session: Session = Depends(get_session)
):
    item = session.get(CartItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")

    fields = body.model_dump(exclude_unset=True)
    if body.priority is not None and body.priority not in cart_repo.PRIORITIES:
        raise HTTPException(422, f"priority must be one of {cart_repo.PRIORITIES}")
    if body.product_id is not None:
        listing = session.get(Product, body.product_id)
        if listing is None or listing.game_id != item.game_id:
            raise HTTPException(404, "Listing not found for this game")
        item.product_id = body.product_id
    if body.unpin:
        item.product_id = None
    if body.quantity is not None:
        item.quantity = max(1, body.quantity)
    if body.priority is not None:
        item.priority = body.priority
    if body.max_price is not None:
        item.max_price = body.max_price
    if body.clear_max_price:
        item.max_price = None
    if "note" in fields:
        note = (body.note or "").strip()
        item.note = note or None

    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/reorder")
def reorder_cart(body: CartReorder, session: Session = Depends(get_session)):
    """Set buy order from a list of ids. Rows left out keep their relative order
    and land after the listed ones."""
    items = cart_repo.active_items(session)
    by_id = {i.id: i for i in items}

    missing = [i for i in body.ids if i not in by_id]
    if missing:
        raise HTTPException(404, f"Unknown cart ids: {missing}")
    if len(set(body.ids)) != len(body.ids):
        raise HTTPException(400, "Duplicate cart ids")

    ordered = [by_id[i] for i in body.ids]
    ordered += [i for i in items if i.id not in set(body.ids)]
    for position, item in enumerate(ordered):
        item.position = position
        session.add(item)
    session.commit()
    return _payload(session, cart_repo.active_items(session))


@router.post("/{item_id}/purchase")
def mark_purchased(item_id: int, session: Session = Depends(get_session)):
    """Move a row out of the queue and onto the record at what it cost."""
    item = session.get(CartItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    rows = cart_repo.enrich(session, [item])
    offer = rows[0]["offer"]
    item.purchased_at = datetime.utcnow()
    item.purchased_price = offer["price"] if offer else None
    session.add(item)
    session.commit()
    session.refresh(item)
    log.info("cart purchased: game %s", item.game_id)
    return item


@router.delete("/{item_id}/purchase")
def unmark_purchased(item_id: int, session: Session = Depends(get_session)):
    """Put a row back in the queue, at the end."""
    item = session.get(CartItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.purchased_at = None
    item.purchased_price = None
    item.position = cart_repo.next_position(session)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}")
def remove_from_cart(item_id: int, session: Session = Depends(get_session)):
    """Archive the row rather than drop it, so re-queuing the game restores it."""
    item = session.get(CartItem, item_id)
    if not item:
        raise HTTPException(404, "Not found")
    item.removed_at = datetime.utcnow()
    session.add(item)
    session.commit()
    log.info("cart removed: item %s (game %s)", item_id, item.game_id)
    return {"ok": True}


@router.put("/budget")
def update_budget(body: BudgetUpdate):
    set_setting(BUDGET_KEY, "" if body.amount is None else str(body.amount))
    return {"budget": _budget()}
