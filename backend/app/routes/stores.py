import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Product, Store
from ..scraper import sync_store

router = APIRouter(prefix="/stores", tags=["stores"])


class StoreCreate(BaseModel):
    id: str
    name: str
    type: str = "shopify"
    base_url: str
    collection_path: str = "/collections/board-games"
    scrape_config: Optional[str] = None


class StorePatch(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    collection_path: Optional[str] = None
    enabled: Optional[bool] = None
    scrape_config: Optional[str] = None


@router.get("/")
def list_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store)).all()


@router.post("/")
def create_store(body: StoreCreate, session: Session = Depends(get_session)):
    store = Store(**body.model_dump(exclude_none=True))
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


@router.patch("/{store_id}")
def update_store(store_id: str, body: StorePatch, session: Session = Depends(get_session)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(store, field, val)
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


@router.delete("/{store_id}")
def delete_store(store_id: str, session: Session = Depends(get_session)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    session.delete(store)
    session.commit()
    return {"ok": True}


@router.post("/sync-all")
async def sync_all_stores(session: Session = Depends(get_session)):
    stores = session.exec(select(Store).where(Store.enabled == True)).all()  # noqa: E712
    results = await asyncio.gather(
        *[sync_store(s) for s in stores], return_exceptions=True
    )
    return [
        {
            "store_id": s.id,
            "result": r if not isinstance(r, Exception) else {"error": str(r)},
        }
        for s, r in zip(stores, results)
    ]


@router.post("/{store_id}/sync")
async def trigger_sync(store_id: str, session: Session = Depends(get_session)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    result = await sync_store(store)
    return result


@router.get("/{store_id}/products")
def list_products(
    store_id: str,
    q: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(Product).where(Product.store_id == store_id)
    products = session.exec(query).all()
    if q:
        ql = q.lower()
        products = [p for p in products if ql in p.title.lower()]
    return products
