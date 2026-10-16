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
            before=before,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


SEEN_KEY = "timeline_seen_at"


class Seen(BaseModel):
    seen_at: datetime | None = None


@router.get("/seen")
def read_seen():
    value = get_setting(SEEN_KEY)
    return {"seen_at": datetime.fromisoformat(value) if value else None}


@router.put("/seen")
def mark_seen(body: Seen):
    """Move the caught-up line; it never moves back, so a stale tab can't undo it."""
    current = get_setting(SEEN_KEY)
    at = _to_datetime(body.seen_at or datetime.utcnow())
    if current and datetime.fromisoformat(current) >= at:
        at = datetime.fromisoformat(current)
    set_setting(SEEN_KEY, at.isoformat())
    return {"seen_at": at}
