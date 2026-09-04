"""Cart data-access: the buy queue and the arithmetic the cart page runs on.

A row names a game, not a listing, so the queue position survives a change of
shop. Which shop a row is quoted at is resolved on read — a pinned listing when
one is chosen, otherwise the cheapest offer that can actually be bought.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import CartItem
from . import catalog as catalog_repo

PRIORITIES = ("must", "normal", "someday")


def _ordered(session: Session, *, purchased: bool) -> list[CartItem]:
    stmt = select(CartItem).where(
        CartItem.purchased_at.is_not(None)
        if purchased
        else CartItem.purchased_at.is_(None)
    )
    if purchased:
        return list(session.exec(stmt.order_by(CartItem.purchased_at.desc())))
    return list(session.exec(stmt.order_by(CartItem.position, CartItem.id)))


def active_items(session: Session) -> list[CartItem]:
    return _ordered(session, purchased=False)


def purchased_items(session: Session) -> list[CartItem]:
    return _ordered(session, purchased=True)


def by_game(session: Session, game_id: int) -> CartItem | None:
    """The un-purchased row for a game, if it is queued."""
    return session.exec(
        select(CartItem).where(
            CartItem.game_id == game_id, CartItem.purchased_at.is_(None)
        )
    ).first()


def next_position(session: Session) -> int:
    last = session.exec(
        select(CartItem)
        .where(CartItem.purchased_at.is_(None))
        .order_by(CartItem.position.desc())
    ).first()
    return (last.position + 1) if last else 0


def pick_offer(compare: dict | None, product_id: int | None) -> dict | None:
    """The offer a row is quoted at: the pinned shop, else cheapest in stock.

    Falls back to the cheapest offer at all when nothing is buyable, so a row
    still carries a price to budget against instead of going blank.
    """
    if not compare:
        return None
    offers = compare.get("offers") or []
    if product_id is not None:
        for offer in offers:
            if offer["product_id"] == product_id:
                return offer
    return compare.get("cheapest_in_stock") or compare.get("cheapest")


def enrich(session: Session, items: list[CartItem]) -> list[dict]:
    """Cart rows joined to the card of the shop each one is quoted at."""
    game_ids = {i.game_id for i in items}
    compares = catalog_repo.compare_summaries(session, game_ids)

    quoted: dict[int, dict | None] = {}
    for item in items:
        quoted[item.id] = pick_offer(compares.get(item.game_id), item.product_id)

    card_ids = [o["product_id"] for o in quoted.values() if o]
    cards = {c["product"].id: c for c in catalog_repo.cards_by_ids(session, card_ids)}

    rows = []
    for item in items:
        offer = quoted[item.id]
        card = cards.get(offer["product_id"]) if offer else None
        rows.append(
            {
                "cart": item,
                "card": card,
                "offer": offer,
                "compare": compares.get(item.game_id),
                # Set only when the shop was chosen by hand — an unpinned row
                # follows the cheapest offer wherever it moves.
                "pinned": item.product_id is not None,
                "price_move": (
                    round(offer["price"] - item.added_price, 2)
                    if offer
                    and offer["price"] is not None
                    and item.added_price is not None
                    else None
                ),
                "over_max": bool(
                    offer
                    and offer["price"] is not None
                    and item.max_price is not None
                    and offer["price"] > item.max_price
                ),
            }
        )
    return rows


def summarise(rows: list[dict], budget: float | None) -> dict:
    """What the cart costs, where it can be bought, and what it would save.

    `cut_index` is the first row the budget cannot reach — everything before it
    is affordable in the current order, which is what makes reordering useful.
    """
    total = 0.0
    in_stock_total = 0.0
    unavailable = 0
    over_max = 0
    savings = 0.0
    by_store: dict[str, dict] = {}
    cut_index = None
    running = 0.0

    for index, row in enumerate(rows):
        offer = row["offer"]
        qty = row["cart"].quantity or 1
        if offer is None or offer["price"] is None:
            unavailable += 1
            continue
        line = offer["price"] * qty
        total += line
        if offer["available"]:
            in_stock_total += line
        else:
            unavailable += 1
        if row["over_max"]:
            over_max += 1

        # What pinning to this shop costs versus the cheapest buyable offer.
        best = (row["compare"] or {}).get("cheapest_in_stock")
        if best and best["product_id"] != offer["product_id"]:
            savings += max(0.0, (offer["price"] - best["price"]) * qty)

        basket = by_store.setdefault(
            offer["store_id"], {"store_id": offer["store_id"], "count": 0, "total": 0.0}
        )
        basket["count"] += qty
        basket["total"] += line

        running += line
        if budget is not None and cut_index is None and running > budget:
            cut_index = index

    return {
        "count": len(rows),
        "total": round(total, 2),
        "in_stock_total": round(in_stock_total, 2),
        "unavailable": unavailable,
        "over_max": over_max,
        "switch_savings": round(savings, 2),
        "budget": budget,
        "budget_remaining": round(budget - total, 2) if budget is not None else None,
        "cut_index": cut_index,
        "by_store": sorted(
            (dict(b, total=round(b["total"], 2)) for b in by_store.values()),
            key=lambda b: -b["total"],
        ),
    }


def cheaper_switches(rows: list[dict]) -> list[dict]:
    """Pinned rows whose shop is beaten by a buyable offer elsewhere."""
    switches = []
    for row in rows:
        if not row["pinned"] or not row["offer"]:
            continue
        best = (row["compare"] or {}).get("cheapest_in_stock")
        if not best or best["product_id"] == row["offer"]["product_id"]:
            continue
        if row["offer"]["price"] is None or best["price"] >= row["offer"]["price"]:
            continue
        switches.append(
            {
                "cart_id": row["cart"].id,
                "from_store": row["offer"]["store_id"],
                "to_store": best["store_id"],
                "to_product_id": best["product_id"],
                "saves": round(
                    (row["offer"]["price"] - best["price"])
                    * (row["cart"].quantity or 1),
                    2,
                ),
            }
        )
    return switches
