from python_ntfy import MessagePriority, NtfyClient, ViewAction

from .config import get_setting
from .logger import get_logger

log = get_logger(__name__)


def _client() -> NtfyClient:
    server = get_setting("ntfy_server") or "https://ntfy.sh"
    topic = get_setting("ntfy_topic") or "board-game-tracker"
    token = get_setting("ntfy_token")
    return NtfyClient(topic=topic, server=server, auth=token or None)


def _latin1_safe(text: str) -> str:
    """ntfy sends the title as an HTTP header, which is latin-1 only. Emoji or
    other non-latin-1 chars there raise UnicodeEncodeError (which previously got
    recorded as a store sync error). Drop anything the header can't carry; use
    `tags` for emoji instead. Message body is sent as UTF-8 and is left alone.
    """
    return text.encode("latin-1", "ignore").decode("latin-1")


def _send(client: NtfyClient, *, kind: str, title: str, **kwargs) -> None:
    """Send a notification, logging success/failure instead of bubbling errors."""
    try:
        client.send(title=_latin1_safe(title), **kwargs)
        log.info(
            "notification sent: %s",
            kind,
            extra={"kind": kind, "title": title},
        )
    except Exception:
        log.exception("notification failed: %s", kind, extra={"kind": kind})


def notify_price_drop(
    product_title: str,
    old_price: float,
    new_price: float,
    product_url: str | None,
    store_name: str,
):
    pct = round((old_price - new_price) / old_price * 100)
    msg = f"{old_price:.0f} → {new_price:.0f}  ({pct}% off)\n{store_name}"
    actions = (
        [ViewAction(label="View on store", url=product_url)] if product_url else None
    )
    _send(
        _client(),
        kind="price_drop",
        message=msg,
        title=f"Price drop: {product_title}",
        priority=MessagePriority.DEFAULT,
        tags=["chart_with_downwards_trend", "shopping"],
        actions=actions,
    )


def notify_back_in_stock(
    product_title: str,
    price: float,
    product_url: str | None,
    store_name: str,
):
    actions = (
        [ViewAction(label="View on store", url=product_url)] if product_url else None
    )
    _send(
        _client(),
        kind="back_in_stock",
        message=f"{price:.0f}  ·  {store_name}",
        title=f"Back in stock: {product_title}",
        priority=MessagePriority.HIGH,
        tags=["white_check_mark", "shopping"],
        actions=actions,
    )


def notify_target_reached(
    product_title: str,
    target_price: float,
    current_price: float,
    product_url: str | None,
    store_name: str,
):
    actions = [ViewAction(label="Buy now", url=product_url)] if product_url else None
    msg = f"Target {target_price:.0f} hit — now {current_price:.0f}\n{store_name}"
    _send(
        _client(),
        kind="target_reached",
        message=msg,
        title=f"Price target hit: {product_title}",
        priority=MessagePriority.HIGH,
        tags=["dart", "shopping"],
        actions=actions,
    )
