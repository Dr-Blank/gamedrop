"""Catalog service — orchestrates the home dashboard from repository feeds."""

from __future__ import annotations

from sqlmodel import Session

from ..filter_engine import Condition
from ..repositories import catalog as repo

WATCHED = Condition(field="is_watched", op="eq", value=True)


def home(session: Session, *, shelf_size: int = 12) -> dict:
    """Everything the landing page needs, in one round trip."""
    return {
        "watchlist": repo.make_cards(
            session, repo.query_products(session, filter_node=WATCHED, limit=shelf_size)
        ),
        "price_drops": repo.price_drops(session, limit=shelf_size),
        "new_additions": repo.new_additions(session, limit=shelf_size),
        "top_discounts": repo.top_discounts(session, limit=shelf_size),
    }
