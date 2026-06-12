import json

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, text
from sqlmodel import Session, select

from ..db import get_session
from ..models import BggCache, PriceSnapshot, Product, ProductOverride, Store

router = APIRouter(prefix="/browse", tags=["browse"])

SORT_OPTIONS = {
    "title": "Name (A–Z)",
    "price_asc": "Price ↑",
    "price_desc": "Price ↓",
    "newest": "Newly added",
    "price_changed": "Price changed recently",
    "discount_pct": "Biggest % discount",
    "discount_abs": "Biggest absolute discount",
    "bgg_rating": "BGG rating ↓",
    "value": "Best value (price ÷ rating)",
    "value_weight": "Price per complexity (÷ weight)",
    "price_rating_rank": "Price × rank score",
}


@router.get("/sorts")
def list_sorts():
    return [{"key": k, "label": v} for k, v in SORT_OPTIONS.items()]


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
    # subquery: latest snapshot per product
    latest_subq = (
        select(
            PriceSnapshot.product_id,
            func.max(PriceSnapshot.recorded_at).label("max_date"),
        )
        .group_by(PriceSnapshot.product_id)
        .subquery()
    )

    # subquery: BGG fields via json_extract (SQLite native)
    bgg_subq = select(
        BggCache.bgg_id,
        func.json_extract(BggCache.data, "$.bgg_rating").label("bgg_rating"),
        func.json_extract(BggCache.data, "$.avg_rating").label("avg_rating"),
        func.json_extract(BggCache.data, "$.avg_weight").label("avg_weight"),
        func.json_extract(BggCache.data, "$.rank").label("rank"),
    ).subquery()

    stmt = (
        select(Product, PriceSnapshot, bgg_subq)
        .join(latest_subq, Product.id == latest_subq.c.product_id, isouter=True)
        .join(
            PriceSnapshot,
            (PriceSnapshot.product_id == latest_subq.c.product_id)
            & (PriceSnapshot.recorded_at == latest_subq.c.max_date),
            isouter=True,
        )
        .join(bgg_subq, Product.bgg_id == bgg_subq.c.bgg_id, isouter=True)
    )

    if q:
        stmt = stmt.where(Product.title.ilike(f"%{q}%"))
    if store_id:
        stmt = stmt.where(Product.store_id == store_id)
    if in_stock is not None:
        stmt = stmt.where(PriceSnapshot.available == in_stock)
    if has_bgg is True:
        stmt = stmt.where(Product.bgg_id.is_not(None))
    if has_bgg is False:
        stmt = stmt.where(Product.bgg_id.is_(None))
    if min_price is not None:
        stmt = stmt.where(PriceSnapshot.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(PriceSnapshot.price <= max_price)
    if min_bgg_rating is not None:
        stmt = stmt.where(bgg_subq.c.bgg_rating >= min_bgg_rating)

    # discount expressions
    _discount_pct = case(
        (
            (PriceSnapshot.compare_at_price > PriceSnapshot.price)
            & (PriceSnapshot.compare_at_price > 0),
            (PriceSnapshot.compare_at_price - PriceSnapshot.price)
            / PriceSnapshot.compare_at_price,
        ),
        else_=0,
    )
    _discount_abs = case(
        (
            PriceSnapshot.compare_at_price > PriceSnapshot.price,
            PriceSnapshot.compare_at_price - PriceSnapshot.price,
        ),
        else_=0,
    )

    match sort:
        case "price_asc":
            stmt = stmt.order_by(PriceSnapshot.price.asc())
        case "price_desc":
            stmt = stmt.order_by(PriceSnapshot.price.desc())
        case "newest":
            stmt = stmt.order_by(Product.updated_at.desc())
        case "price_changed":
            stmt = stmt.order_by(PriceSnapshot.recorded_at.desc())
        case "discount_pct":
            stmt = stmt.order_by(_discount_pct.desc())
        case "discount_abs":
            stmt = stmt.order_by(_discount_abs.desc())
        case "bgg_rating":
            stmt = stmt.order_by(bgg_subq.c.bgg_rating.desc().nulls_last())
        case "value":
            # price ÷ bgg_rating: lower = more rating per rupee spent
            _value = case(
                (
                    bgg_subq.c.bgg_rating > 0,
                    PriceSnapshot.price / bgg_subq.c.bgg_rating,
                ),
                else_=text("9999999"),
            )
            stmt = stmt.order_by(_value.asc())
        case "value_weight":
            # price ÷ avg_weight: lower = cheaper per complexity unit
            _vw = case(
                (
                    bgg_subq.c.avg_weight > 0,
                    PriceSnapshot.price / bgg_subq.c.avg_weight,
                ),
                else_=text("9999999"),
            )
            stmt = stmt.order_by(_vw.asc())
        case "price_rating_rank":
            # composite: normalises price down × rating up × rank up
            # score = bgg_rating / (rank * price) — higher is better deal
            _prr = case(
                (
                    (bgg_subq.c.bgg_rating > 0)
                    & (bgg_subq.c.rank > 0)
                    & (PriceSnapshot.price > 0),
                    bgg_subq.c.bgg_rating / (bgg_subq.c.rank * PriceSnapshot.price),
                ),
                else_=0,
            )
            stmt = stmt.order_by(_prr.desc())
        case _:
            stmt = stmt.order_by(Product.title.asc())

    offset = (page - 1) * limit
    rows = session.exec(stmt.offset(offset).limit(limit)).all()

    # load overrides for products in this page
    product_ids = [r[0].id for r in rows if r[0].id is not None]
    overrides: dict[int, ProductOverride] = {}
    if product_ids:
        for ov in session.exec(
            select(ProductOverride).where(ProductOverride.product_id.in_(product_ids))
        ):
            overrides[ov.product_id] = ov

    results = []
    for row in rows:
        product, snap, *bgg_cols = row
        _bgg_id, bgg_rating, avg_rating, avg_weight, rank = bgg_cols

        bgg_data = None
        if product.bgg_id:
            cached = session.get(BggCache, product.bgg_id)
            if cached:
                try:
                    parsed = json.loads(cached.data)
                    bgg_data = {
                        "bgg_id": product.bgg_id,
                        "name": parsed.get("name"),
                        "avg_rating": parsed.get("avg_rating"),
                        "bgg_rating": parsed.get("bgg_rating"),
                        "rank": parsed.get("rank"),
                        "avg_weight": parsed.get("avg_weight"),
                        "thumbnail": parsed.get("thumbnail"),
                        "bgg_url": parsed.get("bgg_url"),
                    }
                except (json.JSONDecodeError, TypeError):
                    pass

        ov = overrides.get(product.id) if product.id else None

        # compute sort-visible derived values for UI badges
        price = snap.price if snap else None
        cap = snap.compare_at_price if snap else None
        disc_pct = None
        if price and cap and cap > price:
            disc_pct = round((cap - price) / cap * 100, 1)

        results.append(
            {
                "product": product,
                "latest_price": snap,
                "bgg": bgg_data,
                "override": ov,
                "discount_pct": disc_pct,
            }
        )

    return {"items": results, "page": page, "limit": limit}


@router.get("/stores")
def browse_stores(session: Session = Depends(get_session)):
    return session.exec(select(Store).where(Store.enabled)).all()
