from datetime import datetime

from sqlmodel import Session, desc, select

from .adapters.shopify import ShopifyAdapter
from .db import engine
from .logger import get_logger
from .models import PriceSnapshot, Product, Store, SyncLog, WatchlistItem
from .notifier import (
    notify_back_in_stock,
    notify_out_of_stock,
    notify_price_drop,
    notify_price_increase,
    notify_target_reached,
)

log = get_logger(__name__)


def get_adapter(store: Store):
    if store.type == "shopify":
        return ShopifyAdapter(store)
    raise ValueError(f"Unknown store type: {store.type}")


def _check_watchlist(
    session: Session,
    product: Product,
    old_snap: PriceSnapshot | None,
    new_snap: PriceSnapshot,
):
    item = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.product_id == product.id, WatchlistItem.active
        )
    ).first()
    if not item:
        return

    ts = new_snap.recorded_at

    # back in stock
    if old_snap and not old_snap.available and new_snap.available:
        if item.notify_back_in_stock:
            notify_back_in_stock(
                product.title,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                recorded_at=ts,
            )
            item.last_notified_price = new_snap.price
            session.add(item)
        return

    if not new_snap.available:
        if old_snap and old_snap.available and item.notify_out_of_stock:
            notify_out_of_stock(
                product.title,
                old_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                recorded_at=ts,
            )
            session.add(item)
        return

    old_price = old_snap.price if old_snap else None
    if old_price is None:
        return

    if item.target_price is not None:
        if (
            new_snap.price <= item.target_price
            and item.last_notified_price != new_snap.price
            and item.notify_target_reached
        ):
            notify_target_reached(
                product.title,
                item.target_price,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                recorded_at=ts,
            )
            item.last_notified_price = new_snap.price
            session.add(item)
    elif new_snap.price < old_price:
        if item.notify_price_drop and item.last_notified_price != new_snap.price:
            notify_price_drop(
                product.title,
                old_price,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                recorded_at=ts,
            )
            item.last_notified_price = new_snap.price
            session.add(item)
    elif (
        new_snap.price > old_price
        and item.notify_price_increase
        and item.last_notified_price != new_snap.price
    ):
        notify_price_increase(
            product.title,
            old_price,
            new_snap.price,
            product.url,
            product.store_id,
            product_id=product.id,
            recorded_at=ts,
        )
        item.last_notified_price = new_snap.price
        session.add(item)


def _write_sync_result(
    store_id: str,
    started_at: datetime,
    new_products: int = 0,
    updated_products: int = 0,
    price_changes: int = 0,
    error: str | None = None,
):
    now = datetime.utcnow()
    with Session(engine) as session:
        store = session.get(Store, store_id)
        if store:
            if error is None:
                store.last_synced_at = now
                store.last_sync_error = None
            else:
                store.last_sync_error = error
            session.add(store)
        log = SyncLog(
            store_id=store_id,
            started_at=started_at,
            finished_at=now,
            new_products=new_products,
            updated_products=updated_products,
            price_changes=price_changes,
            error=error,
        )
        session.add(log)
        session.commit()


async def sync_store(store: Store) -> dict:
    started_at = datetime.utcnow()
    log.info("sync start", extra={"store_id": store.id})
    adapter = get_adapter(store)

    try:
        raw_products = await adapter.fetch_products()
    except Exception as e:
        error_msg = f"fetch failed: {e}"
        log.error(
            "sync fetch failed: %s", e, extra={"store_id": store.id}, exc_info=True
        )
        _write_sync_result(store.id, started_at, error=error_msg)
        raise

    new_products = 0
    updated_products = 0
    price_changes = 0

    try:
        with Session(engine) as session:
            for p in raw_products:
                existing = session.exec(
                    select(Product).where(
                        Product.store_id == store.id,
                        Product.external_id == p["external_id"],
                    )
                ).first()

                if existing:
                    existing.title = p["title"]
                    existing.url = p["url"]
                    existing.image_url = p.get("image_url") or existing.image_url
                    existing.updated_at = datetime.utcnow()
                    product = existing
                    updated_products += 1
                else:
                    product = Product(
                        store_id=store.id,
                        external_id=p["external_id"],
                        title=p["title"],
                        handle=p.get("handle"),
                        url=p.get("url"),
                        image_url=p.get("image_url"),
                    )
                    session.add(product)
                    session.flush()
                    new_products += 1

                for v in p.get("variants", []):
                    variant_id = v.get("variant_id")
                    latest_q = (
                        select(PriceSnapshot)
                        .where(PriceSnapshot.product_id == product.id)
                        .order_by(desc(PriceSnapshot.recorded_at))
                        .limit(1)
                    )
                    if variant_id is not None:
                        latest_q = latest_q.where(
                            PriceSnapshot.variant_id == variant_id
                        )
                    latest = session.exec(latest_q).first()

                    price_changed = (
                        not latest
                        or latest.price != v["price"]
                        or latest.available != v["available"]
                    )

                    if price_changed:
                        snap = PriceSnapshot(
                            product_id=product.id,
                            variant_id=v.get("variant_id"),
                            variant_title=v.get("variant_title"),
                            price=v["price"],
                            compare_at_price=v.get("compare_at_price"),
                            available=v["available"],
                        )
                        session.add(snap)
                        session.flush()
                        _check_watchlist(session, product, latest, snap)
                        price_changes += 1

            session.commit()
    except Exception as e:
        error_msg = f"db error: {e}"
        log.error(
            "sync db error: %s",
            e,
            extra={"store_id": store.id},
            exc_info=True,
        )
        _write_sync_result(store.id, started_at, error=error_msg)
        raise

    log.info(
        "sync done: +%d new, %d price changes",
        new_products,
        price_changes,
        extra={"store_id": store.id},
    )
    _write_sync_result(
        store.id,
        started_at,
        new_products=new_products,
        updated_products=updated_products,
        price_changes=price_changes,
    )

    return {
        "store_id": store.id,
        "new_products": new_products,
        "updated_products": updated_products,
        "price_changes": price_changes,
        "synced_at": datetime.utcnow().isoformat(),
    }


async def sync_all_stores():
    with Session(engine) as session:
        stores = session.exec(select(Store).where(Store.enabled)).all()
    for store in stores:
        await sync_store(store)
