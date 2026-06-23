from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..filter_engine import BrowseQuery, describe_fields
from ..repositories import catalog as repo

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/fields")
def list_fields(session: Session = Depends(get_session)):
    """Return every filterable/sortable field with type and allowed ops."""
    registry = repo.get_field_registry()
    return describe_fields(registry)


@router.post("/query")
def browse_query(
    body: BrowseQuery,
    session: Session = Depends(get_session),
):
    """Full-power browse: FilterNode tree + priority multi-sort + total count."""
    try:
        rows = repo.query_products(
            session,
            filter_node=body.filters,
            sorts=body.sorts or None,
            page=body.page,
            limit=body.limit,
            include_hidden=body.include_hidden,
        )
        total = repo.count_products(
            session,
            filter_node=body.filters,
            include_hidden=body.include_hidden,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": repo.make_cards(session, rows),
        "page": body.page,
        "limit": body.limit,
        "total": total,
    }


@router.get("/stores")
def browse_stores(session: Session = Depends(get_session)):
    return repo.enabled_stores(session)
