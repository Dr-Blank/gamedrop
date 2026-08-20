"""Watchlist data-access. Cards come from the catalog query — a watch is a
filter on it, not a feed of its own."""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import WatchlistItem


def active_items(session: Session) -> list[WatchlistItem]:
    return session.exec(select(WatchlistItem).where(WatchlistItem.active)).all()
