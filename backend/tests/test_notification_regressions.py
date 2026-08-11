"""Regression tests for notification bugs.

Bugs covered:
1. Duplicate NotificationLog rows when backfill runs after live scraper
   (root cause: sent_at mismatch between live vs backfill rows)
2. Wrong old_price in notifications from multi-variant cross-contamination
   (root cause: global latest snapshot used instead of per-variant latest)
3. sent_at should equal the snapshot's recorded_at, not utcnow()
4. Price increase triggers notification on watched product
5. product_url stored in NotificationLog matches product.url exactly
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import Session, select

from app.models import (
    NotificationLog,
    PriceSnapshot,
    Product,
    Store,
    WatchlistItem,
)
from app.scraper import _check_watchlist

from .factories import make_product

# ── helpers ──────────────────────────────────────────────────────────────────


def _store(session: Session, sid: str = "s1") -> Store:
    s = Store(id=sid, name=sid, type="shopify", base_url=f"https://{sid}.com")
    session.add(s)
    session.commit()
    return s


def _product(
    session: Session,
    store_id: str = "s1",
    url: str = "https://s1.com/catan",
    title: str = "Catan",
) -> Product:
    return make_product(
        session, store_id=store_id, external_id="e1", title=title, url=url
    )


def _snap(
    product_id: int,
    price: float,
    available: bool = True,
    recorded_at: datetime | None = None,
    variant_id: str | None = None,
) -> PriceSnapshot:
    return PriceSnapshot(
        product_id=product_id,
        price=price,
        available=available,
        recorded_at=recorded_at or datetime.utcnow(),
        variant_id=variant_id,
    )


def _watch(
    session: Session,
    game_id: int,
    target_price: float | None = None,
    notify_price_increase: bool = True,
    notify_out_of_stock: bool = True,
) -> WatchlistItem:
    item = WatchlistItem(
        game_id=game_id,
        target_price=target_price,
        active=True,
        notify_price_increase=notify_price_increase,
        notify_out_of_stock=notify_out_of_stock,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


# ── Bug 1: no duplicate rows when backfill runs after live scraper ─────────


def test_backfill_does_not_duplicate_live_notification(client, session: Session):
    """Live scraper fires → DatabaseChannel stores row with sent_at=recorded_at.
    Backfill runs → sees same (product_id, kind, sent_at) key → skips."""
    _store(session)
    product = _product(session)
    _watch(session, product.game_id)

    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    old = _snap(product.id, 500.0, recorded_at=t0)
    new = _snap(product.id, 400.0, recorded_at=t1)
    session.add(old)
    session.add(new)
    session.commit()
    session.refresh(old)
    session.refresh(new)

    # Insert a "live" notification row with sent_at = t1 (snapshot time),
    # as DatabaseChannel now does when it receives recorded_at=snap.recorded_at.
    session.add(
        NotificationLog(
            product_id=product.id,
            kind="price_drop",
            title="Price drop: Catan",
            message="500 → 400 (20% off)\ns1",
            sent_at=t1,
        )
    )
    session.commit()

    count_before = len(
        session.exec(
            select(NotificationLog).where(
                NotificationLog.product_id == product.id,
                NotificationLog.kind == "price_drop",
            )
        ).all()
    )

    # Backfill should see the existing row and skip
    r = client.post("/api/notifications/backfill")
    assert r.status_code == 200
    assert r.json()["inserted"] == 0

    count_after = len(
        session.exec(
            select(NotificationLog).where(
                NotificationLog.product_id == product.id,
                NotificationLog.kind == "price_drop",
            )
        ).all()
    )
    assert count_after == count_before, "backfill created duplicate rows"


# ── Bug 2: sent_at equals snapshot recorded_at ───────────────────────────


def test_database_channel_sent_at_equals_recorded_at(session: Session):
    """DatabaseChannel.send() must store sent_at = recorded_at."""
    from app.channels.database import DatabaseChannel

    snap_time = datetime(2025, 1, 15, 10, 30, 0)
    DatabaseChannel().send(
        kind="price_drop",
        title="Price drop: Catan",
        message="500 → 400",
        product_id=None,
        url=None,
        tags=[],
        recorded_at=snap_time,
    )
    session.expire_all()
    row = session.exec(select(NotificationLog)).first()
    assert row is not None
    assert row.sent_at == snap_time, (
        f"sent_at {row.sent_at!r} != recorded_at {snap_time!r}"
    )


def test_database_channel_sent_at_defaults_to_now_when_no_recorded_at(
    session: Session,
):
    from app.channels.database import DatabaseChannel

    before = datetime.utcnow()
    DatabaseChannel().send(
        kind="price_drop",
        title="T",
        message="M",
        product_id=None,
        url=None,
        tags=[],
    )
    session.expire_all()
    row = session.exec(select(NotificationLog)).first()
    assert row is not None
    assert row.sent_at >= before


# ── Bug 3: multi-variant cross-contamination ──────────────────────────────


def test_price_drop_uses_per_variant_old_price(session: Session):
    """Variant A's price drop must compare against variant A's last snapshot,
    not variant B's. Prevents wrong old_price and spurious notifications."""
    _store(session)
    product = _product(session)
    _watch(session, product.game_id)

    t0 = datetime.utcnow() - timedelta(hours=2)
    t1 = datetime.utcnow() - timedelta(hours=1)

    # Variant A was 500, Variant B was 300
    snap_a_old = _snap(product.id, 500.0, recorded_at=t0, variant_id="va")
    snap_b_old = _snap(product.id, 300.0, recorded_at=t0, variant_id="vb")
    session.add(snap_a_old)
    session.add(snap_b_old)
    session.commit()

    # Variant A drops to 450
    snap_a_new = _snap(product.id, 450.0, recorded_at=t1, variant_id="va")
    session.add(snap_a_new)
    session.flush()

    with patch("app.scraper.notify_price_drop") as mock_drop:
        _check_watchlist(session, product, snap_a_old, snap_a_new)
        mock_drop.assert_called_once()
        called_old_price = mock_drop.call_args[0][1]
        # Must use variant A's old price (500), not variant B's (300)
        assert called_old_price == 500.0, (
            f"used wrong old_price {called_old_price} (expected 500)"
        )


def test_variant_b_does_not_compare_against_variant_a_snapshot(
    session: Session,
):
    """After variant A snapshot is flushed, variant B comparison must still
    use variant B's own last snapshot — not the newly flushed variant A row."""
    _store(session)
    product = _product(session)
    _watch(session, product.game_id)

    t0 = datetime.utcnow() - timedelta(hours=2)

    # Only variant B has history at 300
    snap_b_old = _snap(product.id, 300.0, recorded_at=t0, variant_id="vb")
    session.add(snap_b_old)
    session.commit()

    # Variant A flushes at 450 first (simulates first loop iteration)
    snap_a_new = _snap(
        product.id, 450.0, recorded_at=datetime.utcnow(), variant_id="va"
    )
    session.add(snap_a_new)
    session.flush()

    # Variant B now processes: its last own snapshot is 300, new price is 280
    snap_b_new = _snap(
        product.id, 280.0, recorded_at=datetime.utcnow(), variant_id="vb"
    )
    session.add(snap_b_new)
    session.flush()

    with patch("app.scraper.notify_price_drop") as mock_drop:
        # old_snap passed should be variant B's own previous (snap_b_old)
        _check_watchlist(session, product, snap_b_old, snap_b_new)
        mock_drop.assert_called_once()
        called_old_price = mock_drop.call_args[0][1]
        # Must be 300 (variant B's own old price), not 450 (variant A's)
        assert called_old_price == 300.0, (
            f"cross-contaminated: used old_price {called_old_price} "
            f"from variant A instead of variant B's 300"
        )


# ── Bug 4: price increase triggers notification ───────────────────────────


def test_price_increase_triggers_notification(session: Session):
    _store(session)
    product = _product(session)
    _watch(session, product.game_id, notify_price_increase=True)

    old = _snap(product.id, 400.0)
    new = _snap(product.id, 500.0)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    with patch("app.scraper.notify_price_increase") as mock_increase:
        _check_watchlist(session, product, old, new)
        mock_increase.assert_called_once()
        args = mock_increase.call_args[0]
        assert args[0] == "Catan"
        assert args[1] == 400.0  # old price
        assert args[2] == 500.0  # new price


def test_price_increase_no_notification_when_flag_off(session: Session):
    _store(session)
    product = _product(session)
    item = _watch(session, product.game_id, notify_price_increase=False)
    item.notify_price_increase = False
    session.add(item)
    session.commit()

    old = _snap(product.id, 400.0)
    new = _snap(product.id, 500.0)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    with patch("app.scraper.notify_price_increase") as mock_increase:
        _check_watchlist(session, product, old, new)
        mock_increase.assert_not_called()


# ── Bug 5: product_url in NotificationLog matches product.url ─────────────


def test_notification_url_stored_matches_product_url(session: Session):
    """product_url in NotificationLog must equal the product's url field."""
    _store(session)
    product_url = "https://s1.com/products/catan-base-game"
    product = _product(session, url=product_url)
    _watch(session, product.game_id)

    old = _snap(product.id, 500.0)
    new = _snap(product.id, 400.0)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    captured = {}

    def fake_notify(title, old_p, new_p, url, store, product_id=None, **kw):
        captured["url"] = url

    with patch("app.scraper.notify_price_drop", side_effect=fake_notify):
        _check_watchlist(session, product, old, new)

    assert captured.get("url") == product_url, (
        f"url passed to notify was {captured.get('url')!r}, expected {product_url!r}"
    )


def test_notification_url_is_none_when_product_has_no_url(session: Session):
    _store(session)
    product = _product(session, url=None)  # type: ignore[arg-type]
    product.url = None
    session.add(product)
    session.commit()
    _watch(session, product.game_id)

    old = _snap(product.id, 500.0)
    new = _snap(product.id, 400.0)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    captured = {}

    def fake_notify(title, old_p, new_p, url, store, product_id=None, **kw):
        captured["url"] = url

    with patch("app.scraper.notify_price_drop", side_effect=fake_notify):
        _check_watchlist(session, product, old, new)

    assert captured.get("url") is None


# ── Backfill: price_increase events included ──────────────────────────────


def test_backfill_includes_price_increase(client, session: Session):
    _store(session)
    product = _product(session)
    _watch(session, product.game_id, notify_price_increase=True)

    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    session.add(_snap(product.id, 400.0, recorded_at=t0))
    session.add(_snap(product.id, 500.0, recorded_at=t1))
    session.commit()

    r = client.post("/api/notifications/backfill")
    assert r.status_code == 200
    assert r.json()["inserted"] >= 1

    rows = session.exec(
        select(NotificationLog).where(NotificationLog.kind == "price_increase")
    ).all()
    assert len(rows) >= 1
    # sent_at must equal the snapshot's recorded_at (t1), not utcnow()
    assert abs((rows[0].sent_at - t1).total_seconds()) < 1, (
        f"sent_at {rows[0].sent_at} does not match snapshot time {t1}"
    )


# ── Bug 6: product_id in NotificationLog matches the notified product ─────


def test_notification_product_id_correct_for_two_products(session: Session):
    """Two products each get a price drop. Each NotificationLog row must carry
    its own product's id — no cross-contamination, no wrong id."""
    _store(session)
    product_a = _product(session, url="https://s1.com/a", title="Product A")
    product_b = make_product(
        session, external_id="e2", title="Product B", url="https://s1.com/b"
    )

    _watch(session, product_a.game_id)
    _watch(session, product_b.game_id)

    from app.channels.database import DatabaseChannel

    # Use patch_db_engine via the autouse fixture — engine already swapped.
    db_ch = [DatabaseChannel()]

    from app.notifier import notify_price_drop

    notify_price_drop(
        product_a.title,
        100.0,
        80.0,
        product_a.url,
        "s1",
        product_id=product_a.id,
        channels=db_ch,
    )
    notify_price_drop(
        product_b.title,
        200.0,
        150.0,
        product_b.url,
        "s1",
        product_id=product_b.id,
        channels=db_ch,
    )

    session.expire_all()
    rows = session.exec(select(NotificationLog)).all()
    assert len(rows) == 2

    by_id = {r.product_id: r for r in rows}
    assert product_a.id in by_id, f"No notification for product_a (id={product_a.id})"
    assert product_b.id in by_id, f"No notification for product_b (id={product_b.id})"
    assert "Product A" in by_id[product_a.id].title
    assert "Product B" in by_id[product_b.id].title


def test_notification_product_url_stored_per_product(session: Session):
    """product_url in each NotificationLog row must match that product's url."""
    _store(session)
    product_a = _product(session, url="https://s1.com/game-a", title="Game A")
    product_b = make_product(
        session, external_id="e2", title="Game B", url="https://s1.com/game-b"
    )

    _watch(session, product_a.game_id)
    _watch(session, product_b.game_id)

    from app.channels.database import DatabaseChannel

    db_ch = [DatabaseChannel()]
    from app.notifier import notify_back_in_stock

    notify_back_in_stock(
        product_a.title,
        50.0,
        product_a.url,
        "s1",
        product_id=product_a.id,
        channels=db_ch,
    )
    notify_back_in_stock(
        product_b.title,
        75.0,
        product_b.url,
        "s1",
        product_id=product_b.id,
        channels=db_ch,
    )

    session.expire_all()
    rows = session.exec(select(NotificationLog)).all()
    by_id = {r.product_id: r for r in rows}
    assert by_id[product_a.id].product_url == "https://s1.com/game-a"
    assert by_id[product_b.id].product_url == "https://s1.com/game-b"


def test_list_notifications_api_includes_product_id(client, session: Session):
    """GET /api/notifications must return product_id on each row."""
    _store(session)
    product = _product(session)
    session.add(
        NotificationLog(
            product_id=product.id,
            kind="price_drop",
            title="Price drop: Catan",
            message="100 → 80",
            product_url=product.url,
        )
    )
    session.commit()

    r = client.get("/api/notifications")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["product_id"] == product.id, (
        f"product_id missing or wrong in API response: {items[0]}"
    )
    assert items[0]["product_url"] == product.url


# ── Out of stock notifications ────────────────────────────────────────────


def test_out_of_stock_triggers_notification(session: Session):
    _store(session)
    product = _product(session)
    item = _watch(session, product.game_id)
    item.notify_out_of_stock = True
    session.add(item)
    session.commit()

    old = _snap(product.id, 400.0, available=True)
    new = _snap(product.id, 400.0, available=False)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    with patch("app.scraper.notify_out_of_stock") as mock_oos:
        _check_watchlist(session, product, old, new)
        mock_oos.assert_called_once()
        args = mock_oos.call_args[0]
        assert args[0] == "Catan"  # product title
        assert args[1] == 400.0  # last known price


def test_out_of_stock_no_notification_when_was_already_oos(session: Session):
    _store(session)
    product = _product(session)
    _watch(session, product.game_id)

    old = _snap(product.id, 400.0, available=False)
    new = _snap(product.id, 400.0, available=False)

    with patch("app.scraper.notify_out_of_stock") as mock_oos:
        _check_watchlist(session, product, old, new)
        mock_oos.assert_not_called()


def test_out_of_stock_no_notification_when_flag_off(session: Session):
    _store(session)
    product = _product(session)
    item = _watch(session, product.game_id)
    item.notify_out_of_stock = False
    session.add(item)
    session.commit()

    old = _snap(product.id, 400.0, available=True)
    new = _snap(product.id, 400.0, available=False)
    session.add(old)
    session.flush()
    session.add(new)
    session.flush()

    with patch("app.scraper.notify_out_of_stock") as mock_oos:
        _check_watchlist(session, product, old, new)
        mock_oos.assert_not_called()


def test_backfill_includes_out_of_stock(client, session: Session):
    _store(session)
    product = _product(session)
    item = _watch(session, product.game_id)
    item.notify_out_of_stock = True
    session.add(item)
    session.commit()

    t0 = datetime.utcnow() - timedelta(days=2)
    t1 = datetime.utcnow() - timedelta(days=1)
    session.add(_snap(product.id, 400.0, available=True, recorded_at=t0))
    session.add(_snap(product.id, 400.0, available=False, recorded_at=t1))
    session.commit()

    r = client.post("/api/notifications/backfill")
    assert r.status_code == 200
    assert r.json()["inserted"] >= 1

    rows = session.exec(
        select(NotificationLog).where(NotificationLog.kind == "out_of_stock")
    ).all()
    assert len(rows) >= 1
    assert abs((rows[0].sent_at - t1).total_seconds()) < 1
