from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from app import notifier
from app.models import PriceSnapshot, Product, Store, WatchlistItem
from app.scraper import _check_watchlist

PATCH_DROP = "app.scraper.notify_price_drop"
PATCH_TARGET = "app.scraper.notify_target_reached"
PATCH_STOCK = "app.scraper.notify_back_in_stock"


@pytest.fixture()
def product(session: Session) -> Product:
    session.add(Store(id="s1", name="S1", type="shopify", base_url="https://s1.com"))
    session.commit()
    p = Product(
        store_id="s1", external_id="e1", title="Catan", url="https://s1.com/catan"
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _snap(product_id: int, price: float, available: bool = True) -> PriceSnapshot:
    return PriceSnapshot(product_id=product_id, price=price, available=available)


def _watch(product_id: int, target_price: float | None = None) -> WatchlistItem:
    return WatchlistItem(product_id=product_id, target_price=target_price, active=True)


# --- price drop ---


def test_price_drop_triggers_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 30.0)
    session.add(_watch(product.id))
    session.commit()

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_called_once_with("Catan", 40.0, 30.0, product.url, "s1")


def test_price_drop_no_notification_when_price_unchanged(
    session: Session, product: Product
):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 40.0)
    session.add(_watch(product.id))
    session.commit()

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()


def test_price_drop_no_notification_when_price_higher(
    session: Session, product: Product
):
    old = _snap(product.id, 30.0)
    new = _snap(product.id, 40.0)
    session.add(_watch(product.id))
    session.commit()

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()


def test_price_drop_no_duplicate_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 30.0)
    item = _watch(product.id)
    item.last_notified_price = 30.0  # already notified at this price
    session.add(item)
    session.commit()

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()


def test_price_drop_updates_last_notified_price(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 30.0)
    item = _watch(product.id)
    session.add(item)
    session.commit()
    session.refresh(item)

    with patch(PATCH_DROP):
        _check_watchlist(session, product, old, new)
        session.commit()
        session.refresh(item)
        assert item.last_notified_price == 30.0


# --- target price ---


def test_target_price_hit_triggers_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 19.99)
    session.add(_watch(product.id, target_price=20.0))
    session.commit()

    with patch(PATCH_TARGET) as mock_target:
        _check_watchlist(session, product, old, new)
        mock_target.assert_called_once_with("Catan", 20.0, 19.99, product.url, "s1")


def test_target_price_not_hit_no_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 25.0)
    session.add(_watch(product.id, target_price=20.0))
    session.commit()

    with patch(PATCH_TARGET) as mock_target, patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_target.assert_not_called()
        mock_drop.assert_not_called()


def test_target_price_no_duplicate_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 19.99)
    item = _watch(product.id, target_price=20.0)
    item.last_notified_price = 19.99
    session.add(item)
    session.commit()

    with patch(PATCH_TARGET) as mock_target:
        _check_watchlist(session, product, old, new)
        mock_target.assert_not_called()


# --- back in stock ---


def test_back_in_stock_triggers_notification(session: Session, product: Product):
    old = _snap(product.id, 30.0, available=False)
    new = _snap(product.id, 30.0, available=True)
    session.add(_watch(product.id))
    session.commit()

    with patch(PATCH_STOCK) as mock_stock:
        _check_watchlist(session, product, old, new)
        mock_stock.assert_called_once_with("Catan", 30.0, product.url, "s1")


def test_out_of_stock_no_notification(session: Session, product: Product):
    old = _snap(product.id, 40.0, available=True)
    new = _snap(product.id, 30.0, available=False)
    session.add(_watch(product.id))
    session.commit()

    with patch(PATCH_DROP) as mock_drop, patch(PATCH_STOCK) as mock_stock:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()
        mock_stock.assert_not_called()


# --- watchlist state ---


def test_no_notification_when_not_on_watchlist(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 30.0)

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()


def test_no_notification_when_watchlist_inactive(session: Session, product: Product):
    old = _snap(product.id, 40.0)
    new = _snap(product.id, 30.0)
    item = WatchlistItem(product_id=product.id, active=False)
    session.add(item)
    session.commit()

    with patch(PATCH_DROP) as mock_drop:
        _check_watchlist(session, product, old, new)
        mock_drop.assert_not_called()


# --- ntfy header (latin-1) safety ---


@pytest.mark.parametrize(
    "fn,args",
    [
        (notifier.notify_price_drop, ("Game ✅📉", 40.0, 30.0, "https://x", "S1")),
        (notifier.notify_back_in_stock, ("Game ✅", 30.0, "https://x", "S1")),
        (notifier.notify_target_reached, ("Game 🎯", 20.0, 19.0, "https://x", "S1")),
    ],
)
def test_notification_title_is_latin1_safe(fn, args):
    """Regression: emoji in the ntfy title header raised
    'latin-1 codec can't encode' and got logged as a store sync error."""
    mock_client = MagicMock()
    with patch.object(notifier, "_client", return_value=mock_client):
        fn(*args)

    mock_client.send.assert_called_once()
    title = mock_client.send.call_args.kwargs["title"]
    # Must not raise — this is exactly what python_ntfy does for the header.
    title.encode("latin-1")


def test_notification_failure_is_swallowed_and_logged():
    """A failing send must not bubble up and abort a sync."""
    mock_client = MagicMock()
    mock_client.send.side_effect = RuntimeError("ntfy down")
    with patch.object(notifier, "_client", return_value=mock_client):
        # Should not raise.
        notifier.notify_back_in_stock("Game", 30.0, "https://x", "S1")
