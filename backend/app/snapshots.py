"""Which price readings count.

An ignored reading stays in the table but drops out of charts, stats, filters,
sorts and alerts. A listing whose every reading is ignored falls back to them,
so no listing is ever left priceless.

Shops often list a game out of stock at a placeholder price before it lands.
With `IGNORE_PRE_STOCK` on, a listing's scraped out-of-stock readings from
before its first in-stock reading don't count either. A variant never in stock
keeps them, as the placeholders are all there is.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, exists, not_, or_
from sqlalchemy.orm import aliased
from sqlmodel import select

from .config import get_setting
from .models import PriceSnapshot

MANUAL = "manual"
SCRAPE = "scrape"
IGNORE_PRE_STOCK = "ignore_pre_stock_prices"


def ignore_pre_stock() -> bool:
    return get_setting(IGNORE_PRE_STOCK).strip().lower() != "false"


def effective(snap: type[PriceSnapshot] = PriceSnapshot, pre_stock: bool | None = None):
    """WHERE clause keeping the readings that count, fallback included."""
    if pre_stock is None:
        pre_stock = ignore_pre_stock()
    other = aliased(PriceSnapshot)
    kept = select(other.product_id).where(other.ignored == False)  # noqa: E712
    counted = snap.ignored == False  # noqa: E712
    if pre_stock:
        same_stocked = (
            other.product_id == snap.product_id,
            other.variant_id.is_not_distinct_from(snap.variant_id),
            other.ignored == False,  # noqa: E712
            other.available == True,  # noqa: E712
        )
        placeholder = and_(
            snap.available == False,  # noqa: E712
            snap.source == SCRAPE,
            exists().where(*same_stocked),
            not_(exists().where(*same_stocked, other.recorded_at < snap.recorded_at)),
        )
        counted = and_(counted, not_(placeholder))
    return or_(counted, snap.product_id.notin_(kept))


def split_ignored(
    snaps: list[PriceSnapshot], pre_stock: bool | None = None
) -> tuple[list[PriceSnapshot], list[PriceSnapshot]]:
    """One listing's readings as (counted, ignored), applying the same rules."""
    if pre_stock is None:
        pre_stock = ignore_pre_stock()
    kept = [s for s in snaps if not s.ignored]
    ignored = [s for s in snaps if s.ignored]
    if not kept:
        return ignored, []
    if pre_stock:
        stocked_at: dict[str | None, datetime] = {}
        for s in kept:
            if s.available and (
                s.variant_id not in stocked_at
                or s.recorded_at < stocked_at[s.variant_id]
            ):
                stocked_at[s.variant_id] = s.recorded_at
        kept = [
            s
            for s in kept
            if s.available
            or s.source != SCRAPE
            or s.variant_id not in stocked_at
            or s.recorded_at > stocked_at[s.variant_id]
        ]
    return kept, ignored
