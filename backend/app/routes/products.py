from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..logger import get_logger
from ..models import Product, ProductOverride
from ..repositories import catalog as repo

router = APIRouter(prefix="/products", tags=["products"])
log = get_logger(__name__)


@router.get("/hidden")
def list_hidden(
    page: int = 1,
    limit: int = 48,
    session: Session = Depends(get_session),
):
    items = repo.hidden_products(session, page=page, limit=limit)
    return {"items": items, "page": page, "limit": limit}


def _set_hidden(product_id: int, value: bool, session: Session):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    product.hidden = value
    product.updated_at = datetime.utcnow()
    session.add(product)
    session.commit()
    log.info(
        "product %s %s",
        product_id,
        "hidden" if value else "unhidden",
        extra={"product_id": product_id},
    )
    return {"ok": True, "hidden": value}


@router.post("/{product_id}/image")
async def fetch_product_image(
    product_id: int,
    session: Session = Depends(get_session),
):
    """On-demand: fetch + store one product's image if missing. Returns the URL."""
    from ..models import Store
    from ..scraper import get_adapter

    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if product.image_url:
        return {"image_url": product.image_url}

    store = session.get(Store, product.store_id)
    if not store:
        raise HTTPException(404, "Store not found")

    try:
        image_url = await get_adapter(store).fetch_product_image(product)
    except Exception as e:
        log.warning(
            "image fetch failed: product %s: %s",
            product_id,
            e,
            extra={"product_id": product_id},
        )
        raise HTTPException(502, "Image fetch failed") from e

    if image_url:
        product.image_url = image_url
        product.updated_at = datetime.utcnow()
        session.add(product)
        session.commit()
        log.info(
            "image fetched: product %s",
            product_id,
            extra={"product_id": product_id},
        )
    return {"image_url": image_url}


@router.put("/{product_id}/hide")
def hide_product(product_id: int, session: Session = Depends(get_session)):
    return _set_hidden(product_id, True, session)


@router.delete("/{product_id}/hide")
def unhide_product(product_id: int, session: Session = Depends(get_session)):
    return _set_hidden(product_id, False, session)


class OverrideBody(BaseModel):
    title: str | None = None
    url: str | None = None
    bgg_id: int | None = None
    override_price: float | None = None
    override_available: bool | None = None
    note: str | None = None


@router.put("/{product_id}/override")
def set_override(
    product_id: int,
    body: OverrideBody,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")

    ov = session.get(ProductOverride, product_id)
    if ov is None:
        ov = ProductOverride(product_id=product_id)

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(ov, field, val)
    ov.updated_at = datetime.utcnow()

    session.add(ov)
    session.commit()
    session.refresh(ov)
    log.info(
        "override set: product %s (%s)",
        product_id,
        ", ".join(body.model_dump(exclude_unset=True)) or "cleared fields",
        extra={"product_id": product_id},
    )
    return ov


@router.delete("/{product_id}/override")
def clear_override(
    product_id: int,
    session: Session = Depends(get_session),
):
    ov = session.get(ProductOverride, product_id)
    if not ov:
        raise HTTPException(404, "No override found")
    session.delete(ov)
    session.commit()
    log.info(
        "override cleared: product %s",
        product_id,
        extra={"product_id": product_id},
    )
    return {"ok": True}
