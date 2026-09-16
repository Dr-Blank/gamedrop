import asyncio
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Session, desc, select

from ..adapters.detect import detect_platform
from ..db import get_session
from ..logger import get_logger
from ..models import Product, Store, StoreUrl, SyncLog
from ..scraper import ADAPTERS, sync_store

router = APIRouter(prefix="/stores", tags=["stores"])
log = get_logger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_HOST_RE = re.compile(r"^(?:https?://)?(?:www\.)?([^/:?#]+)")
_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


def normalize_color(v: str | None) -> str | None:
    """`#rrggbb`, or None to fall back to the colour derived from the store id."""
    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    if not _HEX_RE.match(v):
        raise ValueError("color must be a hex value like #4f46e5")
    return v


#: Default listing path per platform; the shapes differ, and a wrong one
#: silently syncs nothing.
DEFAULT_COLLECTION_PATHS = {
    "shopify": "/collections/board-games",
    "woocommerce": "/product-category/board-games",
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


def split_url(raw: str) -> tuple[str, str]:
    """A pasted URL as (origin, listing path). A blank path means none given."""
    parts = urlsplit(raw.strip())
    origin = f"{parts.scheme}://{parts.netloc}".rstrip("/")
    path = parts.path.rstrip("/") if parts.path.strip("/") else ""
    return origin, path


def normalize_path(v: str | None) -> str:
    """A listing path: leading slash, no trailing one. Blank means the whole catalog."""
    v = (v or "").strip()
    if not v:
        return "/"
    if not v.startswith("/"):
        raise ValueError("collection_path must start with /")
    return v.rstrip("/") or "/"


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
    color: str | None = None

    @field_validator("color", mode="before")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return normalize_color(v)

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
        return None if v is None else normalize_path(v)

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
    enabled: bool | None = None
    scrape_config: str | None = None
    color: str | None = None

    @field_validator("color", mode="before")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return normalize_color(v)

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


class StoreUrlCreate(BaseModel):
    collection_path: str = "/"
    label: str | None = None

    @field_validator("collection_path", mode="before")
    @classmethod
    def validate_collection_path(cls, v: str | None) -> str:
        return normalize_path(v)

    @field_validator("label", mode="before")
    @classmethod
    def validate_label(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if len(v) > 128:
            raise ValueError("label must be 128 characters or fewer")
        return v


class StoreUrlPatch(BaseModel):
    collection_path: str | None = None
    label: str | None = None
    enabled: bool | None = None

    @field_validator("collection_path", mode="before")
    @classmethod
    def validate_collection_path(cls, v: str | None) -> str | None:
        return None if v is None else normalize_path(v)


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
        return v


def urls_of(session: Session, store_id: str) -> list[StoreUrl]:
    return list(
        session.exec(
            select(StoreUrl).where(StoreUrl.store_id == store_id).order_by(StoreUrl.id)
        ).all()
    )


def shaped(session: Session, store: Store) -> dict:
    """A store with its listing URLs inlined, which is how the UI reads it."""
    return {**store.model_dump(), "urls": urls_of(session, store.id)}


@router.get("/")
def list_stores(session: Session = Depends(get_session)):
    return [shaped(session, s) for s in session.exec(select(Store)).all()]


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
    """Identify a shop's platform before it's added, and pre-fill the form.

    `matches` names the stores already pointed at this host, so a second
    category URL from a known shop can be attached instead of duplicating it.
    """
    base_url, pasted_path = split_url(body.base_url)
    result = await detect_platform(base_url)
    store_id = derive_store_id(base_url)
    host = host_of(base_url)
    matches = [
        s.id for s in session.exec(select(Store)).all() if host_of(s.base_url) == host
    ]
    return {
        **result,
        "base_url": base_url,
        "id": store_id,
        "id_taken": bool(store_id) and session.get(Store, store_id) is not None,
        "name": derive_store_name(base_url),
        "collection_path": (
            pasted_path or DEFAULT_COLLECTION_PATHS.get(result["type"] or "", "")
        ),
        "matches": matches,
    }


@router.post("/")
def create_store(body: StoreCreate, session: Session = Depends(get_session)):
    if session.get(Store, body.id):
        raise HTTPException(409, "Store ID already exists")
    fields = body.model_dump(exclude_none=True)
    collection_path = fields.pop("collection_path")
    store = Store(**fields)
    session.add(store)
    session.add(StoreUrl(store_id=store.id, collection_path=collection_path))
    session.commit()
    session.refresh(store)
    log.info("store created: %s", store.id, extra={"store_id": store.id})
    return shaped(session, store)


@router.patch("/{store_id}")
def update_store(
    store_id: str, body: StorePatch, session: Session = Depends(get_session)
):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    # Null means "leave it alone", except for colour, where it is how the user
    # asks for the derived default back.
    for field, val in body.model_dump(exclude_unset=True).items():
        if val is None and field != "color":
            continue
        setattr(store, field, val)
    session.add(store)
    session.commit()
    session.refresh(store)
    return shaped(session, store)


@router.delete("/{store_id}")
def delete_store(store_id: str, session: Session = Depends(get_session)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    for url in urls_of(session, store_id):
        session.delete(url)
    session.delete(store)
    session.commit()
    log.info("store deleted: %s", store_id, extra={"store_id": store_id})
    return {"ok": True}


@router.get("/{store_id}/urls")
def list_store_urls(store_id: str, session: Session = Depends(get_session)):
    if not session.get(Store, store_id):
        raise HTTPException(404, "Store not found")
    return urls_of(session, store_id)


@router.post("/{store_id}/urls")
def add_store_url(
    store_id: str, body: StoreUrlCreate, session: Session = Depends(get_session)
):
    if not session.get(Store, store_id):
        raise HTTPException(404, "Store not found")
    existing = session.exec(
        select(StoreUrl).where(
            StoreUrl.store_id == store_id,
            StoreUrl.collection_path == body.collection_path,
        )
    ).first()
    if existing:
        raise HTTPException(409, "Store already syncs that path")
    url = StoreUrl(store_id=store_id, **body.model_dump())
    session.add(url)
    session.commit()
    session.refresh(url)
    log.info(
        "store url added: %s %s",
        store_id,
        url.collection_path,
        extra={"store_id": store_id},
    )
    return url


@router.patch("/{store_id}/urls/{url_id}")
def update_store_url(
    store_id: str,
    url_id: int,
    body: StoreUrlPatch,
    session: Session = Depends(get_session),
):
    url = session.get(StoreUrl, url_id)
    if not url or url.store_id != store_id:
        raise HTTPException(404, "Store URL not found")
    fields = body.model_dump(exclude_unset=True)
    # Checked before the change lands: a flushed clash raises as a 500, not a 409.
    if fields.get("collection_path"):
        clash = session.exec(
            select(StoreUrl).where(
                StoreUrl.store_id == store_id,
                StoreUrl.collection_path == fields["collection_path"],
                StoreUrl.id != url_id,
            )
        ).first()
        if clash:
            raise HTTPException(409, "Store already syncs that path")
    # Null means "leave it alone", except for the label, where it clears it.
    for field, val in fields.items():
        if val is None and field != "label":
            continue
        setattr(url, field, val)
    session.add(url)
    session.commit()
    session.refresh(url)
    return url


@router.delete("/{store_id}/urls/{url_id}")
def delete_store_url(
    store_id: str, url_id: int, session: Session = Depends(get_session)
):
    url = session.get(StoreUrl, url_id)
    if not url or url.store_id != store_id:
        raise HTTPException(404, "Store URL not found")
    session.delete(url)
    session.commit()
    log.info(
        "store url removed: %s %s",
        store_id,
        url.collection_path,
        extra={"store_id": store_id},
    )
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
