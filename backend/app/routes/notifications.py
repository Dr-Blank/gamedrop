from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, asc, desc, select

from ..channels import DatabaseChannel
from ..db import get_session
from ..models import (
    Game,
    NotificationLog,
    PriceSnapshot,
    Product,
    Store,
    WatchlistItem,
)
from ..notifier import (
    notify_back_in_stock,
    notify_out_of_stock,
    notify_price_drop,
    notify_price_increase,
    notify_target_reached,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    limit: int = 20,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(NotificationLog)
        .order_by(desc(NotificationLog.sent_at))
        .offset(offset)
        .limit(limit)
    ).all()
    unread = (
        session.scalar(
            select(func.count(NotificationLog.id)).where(
                NotificationLog.read_at == None  # noqa: E711
            )
        )
        or 0
    )
    return {"items": rows, "unread": unread}


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: int,
    session: Session = Depends(get_session),
):
    row = session.get(NotificationLog, notification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.read_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/read-all")
def mark_all_read(session: Session = Depends(get_session)):
    now = datetime.utcnow()
    result = session.execute(
        update(NotificationLog)
        .where(NotificationLog.read_at == None)  # noqa: E711
        .values(read_at=now)
    )
    session.commit()
    return {"marked": result.rowcount}


@router.post("/backfill")
def backfill_notifications(session: Session = Depends(get_session)):
    """Replay PriceSnapshot history for every watched game's listings, writing
    only to the DatabaseChannel. Idempotent — deduplicates by (product_id, kind,
    sent_at) where sent_at == snap.recorded_at (set via recorded_at param)."""
    db_only: list = [DatabaseChannel()]
    inserted = 0

    for item in session.exec(select(WatchlistItem)).all():
        game = session.get(Game, item.game_id)
        if not game:
            continue
        listings = session.exec(
            select(Product).where(Product.game_id == item.game_id)
        ).all()
        for product in listings:
            inserted += _replay_listing(session, item, game, product, db_only)

    return {"inserted": inserted}


def _replay_listing(session, item, game, product, db_only) -> int:
    """Backfill one shop's history for a watched game."""
    inserted = 0
    store = session.get(Store, product.store_id)
    store_name = store.id if store else product.store_id

    snaps = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product.id)
        .order_by(asc(PriceSnapshot.recorded_at))
    ).all()

    # Dedup key: (product_id, kind, sent_at). Because DatabaseChannel stores
    # sent_at = recorded_at, this matches both live and backfill rows.
    existing_keys: set[tuple] = {
        (r.product_id, r.kind, r.sent_at)
        for r in session.exec(
            select(NotificationLog).where(NotificationLog.product_id == product.id)
        ).all()
    }

    prev: PriceSnapshot | None = None
    for snap in snaps:
        kind: str | None = None

        if prev and not prev.available and snap.available:
            kind = "back_in_stock"
        elif prev and prev.available and not snap.available:
            kind = "out_of_stock"
        elif snap.available and prev:
            if item.target_price is not None:
                if snap.price <= item.target_price:
                    kind = "target_reached"
            elif snap.price < prev.price:
                kind = "price_drop"
            elif snap.price > prev.price:
                kind = "price_increase"

        if kind:
            key = (product.id, kind, snap.recorded_at)
            if key not in existing_keys:
                kwargs = {
                    "product_id": product.id,
                    "game_id": game.id,
                    "channels": db_only,
                    "recorded_at": snap.recorded_at,
                }
                if kind == "back_in_stock" and item.notify_back_in_stock:
                    notify_back_in_stock(
                        game.title,
                        snap.price,
                        product.url,
                        store_name,
                        **kwargs,
                    )
                    existing_keys.add(key)
                    inserted += 1
                elif kind == "target_reached" and item.notify_target_reached:
                    notify_target_reached(
                        game.title,
                        item.target_price,  # type: ignore[arg-type]
                        snap.price,
                        product.url,
                        store_name,
                        **kwargs,
                    )
                    existing_keys.add(key)
                    inserted += 1
                elif kind == "price_drop" and item.notify_price_drop:
                    notify_price_drop(
                        game.title,
                        prev.price,  # type: ignore[union-attr]
                        snap.price,
                        product.url,
                        store_name,
                        **kwargs,
                    )
                    existing_keys.add(key)
                    inserted += 1
                elif kind == "price_increase" and item.notify_price_increase:
                    notify_price_increase(
                        game.title,
                        prev.price,  # type: ignore[union-attr]
                        snap.price,
                        product.url,
                        store_name,
                        **kwargs,
                    )
                    existing_keys.add(key)
                    inserted += 1
                elif kind == "out_of_stock" and item.notify_out_of_stock:
                    notify_out_of_stock(
                        game.title,
                        prev.price,  # type: ignore[union-attr]
                        product.url,
                        store_name,
                        **kwargs,
                    )
                    existing_keys.add(key)
                    inserted += 1

        prev = snap

    return inserted
