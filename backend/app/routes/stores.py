import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Session, desc, select

from ..adapters.detect import detect_platform
from ..db import get_session
from ..logger import get_logger
from ..models import Product, Store, SyncLog
from ..scraper import ADAPTERS, sync_store

router = APIRouter(prefix="/stores", tags=["stores"])
log = get_logger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_HOST_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/:?#]+)")

#: Default listing path per platform; the shapes differ, and a wrong one
#: silently syncs nothing.
DEFAULT_COLLECTION_PATHS = {
    "shopify": "/collections/board-games",
    "woocommerce": "/product-category/board-games/",
}


def host_of(base_url: str) -> str:
    """Hostname of a URL, without `www.`."""
    match = _HOST_RE.match((base_url or "").strip())
    return match.group(1).rstrip("/") if match else ""


def derive_store_id(base_url: str) -> str:
    """Store slug from a URL's first host label."""
    host = host_of(base_url)
    label = host.split(".")[0] if host else ""
    return re.sub(r"[^a-z0-9-]", "-", label.lower()).strip("-")


def derive_store_name(base_url: str) -> str:
    """Human name from a URL's first host label."""
    slug = derive_store_id(base_url)
    return " ".join(part.capitalize() for part in slug.split("-") if part)


class StoreCreate(BaseModel):
    # Blank id/name are derived from base_url.
    id: str = ""
    name: str = ""
    type: str = "shopify"
    base_url: str
    collection_path: str | None = None
    scrape_config: str | None = None

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("base_url must start with http:// or https://")
        if not host_of(v):
            raise ValueError("base_url must include a hostname")
        return v.rstrip("/")

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ADAPTERS:
            raise ValueError(f"type must be one of: {', '.join(sorted(ADAPTERS))}")
        return v

    @field_validator("collection_path", mode="before")
    @classmethod
    def validate_collection_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith("/"):
            raise ValueError("collection_path must start with /")
        return v

    @model_validator(mode="after")
    def fill_defaults(self):
        self.id = (self.id or "").strip() or derive_store_id(self.base_url)
        self.name = (self.name or "").strip() or derive_store_name(self.base_url)
        if not self.id:
            raise ValueError("could not derive an id from base_url — set one")
        if len(self.id) > 64:
            raise ValueError("id must be 64 characters or fewer")
        if not _SLUG_RE.match(self.id):
            raise ValueError("id must match [a-z0-9-]+")
        if len(self.name) > 128:
            raise ValueError("name must be 128 characters or fewer")
        if self.collection_path is None:
            self.collection_path = DEFAULT_COLLECTION_PATHS[self.type]
        return self


class StorePatch(BaseModel):
    name: str | None = None
    type: str | None = None
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

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ADAPTERS:
            raise ValueError(f"type must be one of: {', '.join(sorted(ADAPTERS))}")
        return v

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("collection_path", mode="before")
    @classmethod
    def validate_collection_path(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith("/"):
            raise ValueError("collection_path must start with /")
        return v


class DetectBody(BaseModel):
    base_url: str

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("base_url must not be blank")
        if not (v.startswith("https://") or v.startswith("http://")):
            v = f"https://{v}"
        if not host_of(v):
            raise ValueError("base_url must include a hostname")
        return v.rstrip("/")


@router.get("/")
def list_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store)).all()


@router.get("/types")
def list_store_types():
    """Platforms this build can sync, with each one's default listing path."""
    return [
        {
            "type": name,
            "default_collection_path": DEFAULT_COLLECTION_PATHS.get(name, ""),
        }
        for name in sorted(ADAPTERS)
    ]


@router.post("/detect")
async def detect_store(body: DetectBody, session: Session = Depends(get_session)):
    """Identify a shop's platform before it's added, and pre-fill the form."""
    result = await detect_platform(body.base_url)
    store_id = derive_store_id(body.base_url)
    return {
        **result,
        "base_url": body.base_url,
        "id": store_id,
        "id_taken": bool(store_id) and session.get(Store, store_id) is not None,
        "name": derive_store_name(body.base_url),
        "collection_path": DEFAULT_COLLECTION_PATHS.get(result["type"] or "", ""),
    }


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
    products = session.exec(select(Product).where(Product.store_id == store_id)).all()
    if q:
        ql = q.lower()
        products = [p for p in products if ql in p.title.lower()]
    return products
