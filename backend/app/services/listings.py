"""Deleting listings, and the rows that hang off them.

A listing removed on its own would leave its snapshots, overrides and watch
state behind, so every delete goes through here.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..logger import get_logger
from ..models import (
    CartItem,
    MergeRejection,
    NotificationLog,
    PriceSnapshot,
    Product,
    ProductOverride,
    Store,
    WatchListingState,
)

log = get_logger(__name__)


def _orphan_clause():
    """Listings whose store row is gone."""
    return Product.store_id.notin_(select(Store.id))


def delete_products(session: Session, product_ids: list[int]) -> int:
    """Delete listings and everything keyed on them. Returns how many went.

    Queue rows and notifications keep their history — their listing reference is
    cleared instead, so a re-added shop can fill it back in.
    """
    if not product_ids:
        return 0

    for snap in session.exec(
        select(PriceSnapshot).where(PriceSnapshot.product_id.in_(product_ids))
    ):
        session.delete(snap)
    for override in session.exec(
        select(ProductOverride).where(ProductOverride.product_id.in_(product_ids))
    ):
        session.delete(override)
    for state in session.exec(
        select(WatchListingState).where(WatchListingState.product_id.in_(product_ids))
    ):
        session.delete(state)
    for rejection in session.exec(
        select(MergeRejection).where(
            or_(
                MergeRejection.product_a_id.in_(product_ids),
                MergeRejection.product_b_id.in_(product_ids),
            )
        )
    ):
        session.delete(rejection)

    for entry in session.exec(
        select(NotificationLog).where(NotificationLog.product_id.in_(product_ids))
    ):
        entry.product_id = None
        session.add(entry)
    for item in session.exec(
        select(CartItem).where(CartItem.product_id.in_(product_ids))
    ):
        item.product_id = None
        session.add(item)

    deleted = 0
    for product in session.exec(select(Product).where(Product.id.in_(product_ids))):
        session.delete(product)
        deleted += 1
    session.flush()
    return deleted


def delete_store_listings(session: Session, store_id: str) -> int:
    """Delete every listing a store brought in."""
    ids = list(session.exec(select(Product.id).where(Product.store_id == store_id)))
    deleted = delete_products(session, ids)
    if deleted:
        log.info(
            "listings deleted with store %s: %d",
            store_id,
            deleted,
            extra={"store_id": store_id},
        )
    return deleted


def orphan_summary(session: Session) -> dict:
    """Listings left behind by removed stores, counted per missing store id."""
    rows = session.exec(
        select(Product.store_id, func.count(Product.id))
        .where(_orphan_clause())
        .group_by(Product.store_id)
        .order_by(Product.store_id)
    ).all()
    stores = [{"store_id": store_id, "listings": int(n)} for store_id, n in rows]
    games = session.exec(
        select(func.count(func.distinct(Product.game_id))).where(_orphan_clause())
    ).one()
    return {
        "listings": sum(s["listings"] for s in stores),
        "games": int(games),
        "stores": stores,
    }


def delete_orphan_listings(session: Session) -> int:
    """Delete every listing whose store is gone."""
    ids = list(session.exec(select(Product.id).where(_orphan_clause())))
    deleted = delete_products(session, ids)
    if deleted:
        log.info("orphaned listings cleaned up: %d", deleted)
    return deleted
