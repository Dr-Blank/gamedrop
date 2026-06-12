from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..repositories import catalog as repo

router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("/sorts")
def list_sorts():
    return [{"key": k, "label": v} for k, v in repo.SORT_OPTIONS.items()]


@router.get("/")
def browse(
    q: str | None = None,
    store_id: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
    has_bgg: bool | None = None,
    min_bgg_rating: float | None = None,
    sort: str = "title",
    page: int = 1,
    limit: int = 48,
    session: Session = Depends(get_session),
):
    filters = repo.CatalogFilters(
        q=q,
        store_id=store_id,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        has_bgg=has_bgg,
        min_bgg_rating=min_bgg_rating,
    )
    rows = repo.query_products(
        session, filters=filters, sort=sort, page=page, limit=limit
    )
    return {"items": repo.make_cards(session, rows), "page": page, "limit": limit}


@router.get("/stores")
def browse_stores(session: Session = Depends(get_session)):
    return repo.enabled_stores(session)
