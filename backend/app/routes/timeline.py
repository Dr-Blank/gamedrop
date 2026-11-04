import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from ..config import get_setting, set_setting
from ..db import get_session
from ..filter_engine import _to_datetime
from ..services.timeline import KINDS, change_events

router = APIRouter(prefix="/timeline", tags=["timeline"])


def _csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


@router.get("/events")
def list_events(
    since: str | None = None,
    until: str | None = None,
    stores: str | None = None,
    kinds: str | None = None,
    min_pct: float | None = None,
    watchlist: bool = False,
    include_hidden: bool = False,
    before: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    wanted = _csv(kinds)
    unknown = set(wanted) - set(KINDS)
    if unknown:
        raise HTTPException(422, f"Unknown kinds: {', '.join(sorted(unknown))}")
    try:
        return change_events(
            session,
            since=_to_datetime(since) if since else None,
            until=_to_datetime(until) if until else None,
            store_ids=_csv(stores),
            kinds=wanted,
            min_pct=min_pct,
            watchlist=watchlist,
            include_hidden=include_hidden,
            before=before,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


SEEN_KEY = "timeline_seen_at"
SEEN_STORES_KEY = "timeline_seen_stores"


class Seen(BaseModel):
    seen_at: datetime | None = None
    store_ids: list[str] = []


def _store_lines() -> dict[str, datetime]:
    saved = json.loads(get_setting(SEEN_STORES_KEY) or "{}")
    return {store: datetime.fromisoformat(at) for store, at in saved.items()}


@router.get("/seen")
def read_seen():
    value = get_setting(SEEN_KEY)
    return {
        "seen_at": datetime.fromisoformat(value) if value else None,
        "stores": _store_lines(),
    }


@router.put("/seen")
def mark_seen(body: Seen):
    """Move the caught-up line, or only these shops' lines.

    A line never moves back, so a stale tab can't undo it.
    """
    at = _to_datetime(body.seen_at or datetime.utcnow())
    if body.store_ids:
        lines = _store_lines()
        for store in body.store_ids:
            lines[store] = max(at, lines.get(store, at))
        saved = {store: line.isoformat() for store, line in lines.items()}
        set_setting(SEEN_STORES_KEY, json.dumps(saved))
    else:
        current = get_setting(SEEN_KEY)
        if current and datetime.fromisoformat(current) >= at:
            at = datetime.fromisoformat(current)
        set_setting(SEEN_KEY, at.isoformat())
    return read_seen()
