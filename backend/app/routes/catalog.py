"""Dashboard + discovery feeds + global search.

Thin HTTP layer over the catalog repository/service. Every endpoint returns
the same enriched card shape used by browse, so the frontend renders one card
component everywhere.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..repositories import catalog as repo
from ..services import catalog as service

router = APIRouter(tags=["catalog"])


@router.get("/home")
def home(shelf_size: int = 12, session: Session = Depends(get_session)):
    return service.home(session, shelf_size=shelf_size)


@router.get("/feed/drops")
def feed_drops(
    page: int = 1,
    limit: int = 24,
    in_stock: bool = False,
    session: Session = Depends(get_session),
):
    items = repo.price_drops(session, page=page, limit=limit, in_stock_only=in_stock)
    return {"items": items, "page": page, "limit": limit}


@router.get("/feed/new")
def feed_new(page: int = 1, limit: int = 24, session: Session = Depends(get_session)):
    items = repo.new_additions(session, page=page, limit=limit)
    return {"items": items, "page": page, "limit": limit}


@router.get("/feed/discounts")
def feed_discounts(
    page: int = 1, limit: int = 24, session: Session = Depends(get_session)
):
    items = repo.top_discounts(session, page=page, limit=limit)
    return {"items": items, "page": page, "limit": limit}


@router.get("/search")
def search(q: str, limit: int = 24, session: Session = Depends(get_session)):
    return {"q": q, "items": repo.search(session, q=q, limit=limit)}
