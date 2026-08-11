from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlmodel import Session, desc, select

from . import db as _db
from .adapters.shopify import ShopifyAdapter
from .adapters.woocommerce import WooCommerceAdapter
from .logger import get_logger
from .models import (
    Game,
    PriceSnapshot,
    Product,
    Store,
    SyncLog,
    WatchListingState,
    WatchlistItem,
)
from .notifier import (
    notify_back_in_stock,
    notify_out_of_stock,
    notify_price_drop,
    notify_price_increase,
    notify_target_reached,
)

log = get_logger(__name__)


ADAPTERS = {
    "shopify": ShopifyAdapter,
    "woocommerce": WooCommerceAdapter,
}


def get_adapter(store: Store):
    adapter = ADAPTERS.get(store.type)
    if adapter is None:
        raise ValueError(f"Unknown store type: {store.type}")
    return adapter(store)


# A queued notification: (function, args, kwargs), dispatched after commit.
PendingNotification = tuple[Callable[..., None], tuple, dict[str, Any]]


def dispatch_pending(pending: list[PendingNotification]) -> None:
    """Fire queued notifications. Must run *outside* the sync transaction —
    every channel opens its own connection, and SQLite allows a single writer,
    so dispatching mid-transaction fails with 'database is locked'."""
    for fn, args, kwargs in pending:
        fn(*args, **kwargs)
    pending.clear()


def _remember(session: Session, state: WatchListingState, price: float | None) -> None:
    state.last_notified_price = price
    state.updated_at = datetime.utcnow()
    session.add(state)


def _check_watchlist(
    session: Session,
    product: Product,
    old_snap: PriceSnapshot | None,
    new_snap: PriceSnapshot,
    pending: list[PendingNotification] | None = None,
):
    """Queue notifications for a price change onto `pending`.

    The watch belongs to the game, but alerts are per listing — every shop's
    move is reported, so `WatchListingState` remembers what each shop was last
    announced at.

    With no `pending` list the notifications fire immediately — only safe when
    the caller holds no open write transaction.
    """

    def emit(fn: Callable[..., None], *args, **kwargs) -> None:
        if pending is None:
            fn(*args, **kwargs)
        else:
            pending.append((fn, args, kwargs))

    item = session.exec(
        select(WatchlistItem).where(
            WatchlistItem.game_id == product.game_id, WatchlistItem.active
        )
    ).first()
    if not item:
        return

    game = session.get(Game, product.game_id)
    title = game.title if game else product.title
    state = session.get(WatchListingState, (item.id, product.id))
    if state is None:
        state = WatchListingState(watch_id=item.id, product_id=product.id)

    ts = new_snap.recorded_at

    # back in stock
    if old_snap and not old_snap.available and new_snap.available:
        if item.notify_back_in_stock:
            emit(
                notify_back_in_stock,
                title,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                game_id=product.game_id,
                recorded_at=ts,
            )
            _remember(session, state, new_snap.price)
        return

    if not new_snap.available:
        if old_snap and old_snap.available and item.notify_out_of_stock:
            emit(
                notify_out_of_stock,
                title,
                old_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                game_id=product.game_id,
                recorded_at=ts,
            )
            _remember(session, state, None)
        return

    old_price = old_snap.price if old_snap else None
    if old_price is None:
        return

    already_told = state.last_notified_price == new_snap.price

    if item.target_price is not None:
        if (
            new_snap.price <= item.target_price
            and not already_told
            and item.notify_target_reached
        ):
            emit(
                notify_target_reached,
                title,
                item.target_price,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                game_id=product.game_id,
                recorded_at=ts,
            )
            _remember(session, state, new_snap.price)
    elif new_snap.price < old_price:
        if item.notify_price_drop and not already_told:
            emit(
                notify_price_drop,
                title,
                old_price,
                new_snap.price,
                product.url,
                product.store_id,
                product_id=product.id,
                game_id=product.game_id,
                recorded_at=ts,
            )
            _remember(session, state, new_snap.price)
    elif new_snap.price > old_price and item.notify_price_increase and not already_told:
        emit(
            notify_price_increase,
            title,
            old_price,
            new_snap.price,
            product.url,
            product.store_id,
            product_id=product.id,
            game_id=product.game_id,
            recorded_at=ts,
        )
        _remember(session, state, new_snap.price)


def _write_sync_result(
    store_id: str,
    started_at: datetime,
    new_products: int = 0,
    updated_products: int = 0,
    price_changes: int = 0,
    error: str | None = None,
):
    now = datetime.utcnow()
    with Session(_db.engine) as session:
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
    pending: list[PendingNotification] = []

    try:
        with Session(_db.engine) as session:
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
                    game = Game(title=p["title"])
                    session.add(game)
                    session.flush()
                    product = Product(
                        store_id=store.id,
                        game_id=game.id,
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
                        _check_watchlist(session, product, latest, snap, pending)
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

    # Transaction is closed — channels can now take the write lock themselves.
    dispatch_pending(pending)

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
    with Session(_db.engine) as session:
        stores = session.exec(select(Store).where(Store.enabled)).all()
    for store in stores:
        await sync_store(store)
