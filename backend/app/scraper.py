from datetime import datetime

from sqlmodel import Session, desc, select

from .adapters.shopify import ShopifyAdapter
from .db import engine
from .models import Product, PriceSnapshot, Store, WatchlistItem
from .notifier import notify_back_in_stock, notify_price_drop, notify_target_reached


def get_adapter(store: Store):
    if store.type == "shopify":
        return ShopifyAdapter(store)
    raise ValueError(f"Unknown store type: {store.type}")


def _check_watchlist(session: Session, product: Product, old_snap: PriceSnapshot | None, new_snap: PriceSnapshot):
    item = session.exec(
        select(WatchlistItem)
        .where(WatchlistItem.product_id == product.id, WatchlistItem.active == True)
    ).first()
    if not item:
        return

    # back in stock
    if old_snap and not old_snap.available and new_snap.available:
        notify_back_in_stock(product.title, new_snap.price, product.url, product.store_id)
        item.last_notified_price = new_snap.price
        session.add(item)
        return

    if not new_snap.available:
        return

    old_price = old_snap.price if old_snap else None

    if item.target_price is not None:
        # notify once when price crosses target (avoid re-notifying same price)
        if (
            new_snap.price <= item.target_price
            and item.last_notified_price != new_snap.price
        ):
            notify_target_reached(product.title, item.target_price, new_snap.price, product.url, product.store_id)
            item.last_notified_price = new_snap.price
            session.add(item)
    elif old_price and new_snap.price < old_price:
        # any drop — notify once per price level
        if item.last_notified_price != new_snap.price:
            notify_price_drop(product.title, old_price, new_snap.price, product.url, product.store_id)
            item.last_notified_price = new_snap.price
            session.add(item)


async def sync_store(store: Store) -> dict:
    adapter = get_adapter(store)
    raw_products = await adapter.fetch_products()

    new_products = 0
    updated_products = 0
    price_changes = 0

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
                )
                session.add(product)
                session.flush()
                new_products += 1

            for v in p.get("variants", []):
                latest = session.exec(
                    select(PriceSnapshot)
                    .where(PriceSnapshot.product_id == product.id)
                    .order_by(desc(PriceSnapshot.recorded_at))
                    .limit(1)
                ).first()

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

    return {
        "store_id": store.id,
        "new_products": new_products,
        "updated_products": updated_products,
        "price_changes": price_changes,
        "synced_at": datetime.utcnow().isoformat(),
    }


async def sync_all_stores():
    with Session(engine) as session:
        stores = session.exec(select(Store).where(Store.enabled == True)).all()
    for store in stores:
        await sync_store(store)
