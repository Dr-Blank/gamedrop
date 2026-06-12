"""Catalog service — orchestrates the home dashboard from repository feeds."""

from __future__ import annotations

from sqlmodel import Session

from ..repositories import catalog as repo
from ..repositories import watchlist as wl_repo


def home(session: Session, *, shelf_size: int = 12) -> dict:
    """Everything the landing page needs, in one round trip."""
    return {
        "watchlist": wl_repo.cards(session, limit=shelf_size),
        "price_drops": repo.price_drops(session, limit=shelf_size),
        "new_additions": repo.new_additions(session, limit=shelf_size),
        "top_discounts": repo.top_discounts(session, limit=shelf_size),
    }
