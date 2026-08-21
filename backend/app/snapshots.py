"""Which price readings count.

An ignored reading stays in the table but drops out of charts, stats, filters,
sorts and alerts. A listing whose every reading is ignored falls back to them,
so no listing is ever left priceless.
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlmodel import select

from .models import PriceSnapshot

MANUAL = "manual"
SCRAPE = "scrape"


def effective(snap: type[PriceSnapshot] = PriceSnapshot):
    """WHERE clause keeping the readings that count, fallback included."""
    other = aliased(PriceSnapshot)
    kept = select(other.product_id).where(other.ignored == False)  # noqa: E712
    return or_(snap.ignored == False, snap.product_id.notin_(kept))  # noqa: E712


def split_ignored(
    snaps: list[PriceSnapshot],
) -> tuple[list[PriceSnapshot], list[PriceSnapshot]]:
    """One listing's readings as (counted, ignored), applying the same fallback."""
    kept = [s for s in snaps if not s.ignored]
    ignored = [s for s in snaps if s.ignored]
    return (kept, ignored) if kept else (ignored, [])
