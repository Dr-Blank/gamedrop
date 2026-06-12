from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import Product, ProductOverride

router = APIRouter(prefix="/products", tags=["products"])


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
    return {"ok": True}
