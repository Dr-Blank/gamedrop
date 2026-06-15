import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, desc, select

from ..db import get_session
from ..logger import get_logger
from ..models import Product, Store, SyncLog
from ..scraper import sync_store

router = APIRouter(prefix="/stores", tags=["stores"])
log = get_logger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class StoreCreate(BaseModel):
    id: str
    name: str
    type: str = "shopify"
    base_url: str
    collection_path: str = "/collections/board-games"
    scrape_config: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("id must not be blank")
        if len(v) > 64:
            raise ValueError("id must be 64 characters or fewer")
        if not _SLUG_RE.match(v):
            raise ValueError("id must match [a-z0-9-]+")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        if len(v) > 128:
            raise ValueError("name must be 128 characters or fewer")
        return v

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @field_validator("collection_path", mode="before")
    @classmethod
    def validate_collection_path(cls, v: str) -> str:
        if v and not v.startswith("/"):
            raise ValueError("collection_path must start with /")
        return v


class StorePatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    collection_path: str | None = None
    enabled: bool | None = None
    scrape_config: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        if len(v) > 128:
            raise ValueError("name must be 128 characters or fewer")
        return v

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


@router.get("/")
def list_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store)).all()


@router.post("/")
def create_store(body: StoreCreate, session: Session = Depends(get_session)):
    if session.get(Store, body.id):
        raise HTTPException(409, "Store ID already exists")
    store = Store(**body.model_dump(exclude_none=True))
    session.add(store)
    session.commit()
    session.refresh(store)
    log.info("store created: %s", store.id, extra={"store_id": store.id})
    return store


@router.patch("/{store_id}")
def update_store(
    store_id: str, body: StorePatch, session: Session = Depends(get_session)
):
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
    log.info("store deleted: %s", store_id, extra={"store_id": store_id})
    return {"ok": True}


@router.post("/sync-all")
async def sync_all_stores(session: Session = Depends(get_session)):
    stores = session.exec(select(Store).where(Store.enabled == True)).all()  # noqa: E712
    log.info("manual sync-all triggered: %d stores", len(stores))
    results = await asyncio.gather(
        *[sync_store(s) for s in stores], return_exceptions=True
    )
    return [
        {
            "store_id": s.id,
            "result": r if not isinstance(r, Exception) else {"error": str(r)},
        }
        for s, r in zip(stores, results, strict=False)
    ]


@router.post("/{store_id}/sync")
async def trigger_sync(store_id: str, session: Session = Depends(get_session)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    log.info("manual sync triggered: %s", store_id, extra={"store_id": store_id})
    result = await sync_store(store)
    return result


@router.get("/{store_id}/logs")
def get_sync_logs(
    store_id: str, limit: int = 20, session: Session = Depends(get_session)
):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    logs = session.exec(
        select(SyncLog)
        .where(SyncLog.store_id == store_id)
        .order_by(desc(SyncLog.started_at))
        .limit(limit)
    ).all()
    return logs


@router.get("/{store_id}/products")
def list_products(
    store_id: str,
    q: str | None = None,
    session: Session = Depends(get_session),
):
    query = select(Product).where(Product.store_id == store_id)
    products = session.exec(query).all()
    if q:
        ql = q.lower()
        products = [p for p in products if ql in p.title.lower()]
    return products
