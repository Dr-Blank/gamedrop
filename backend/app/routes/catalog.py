"""Global search.

Ranking is the one thing a browse query cannot express, so it keeps its own
endpoint; every other feed is a filter and lives in /browse/query.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..repositories import catalog as repo

router = APIRouter(tags=["catalog"])


@router.get("/search")
def search(q: str, limit: int = 24, session: Session = Depends(get_session)):
    return {"q": q, "items": repo.search(session, q=q, limit=limit)}
