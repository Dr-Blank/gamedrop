from python_ntfy import MessagePriority, NtfyClient, ViewAction

from .config import get_setting


def _client() -> NtfyClient:
    server = get_setting("ntfy_server") or "https://ntfy.sh"
    topic = get_setting("ntfy_topic") or "board-game-tracker"
    token = get_setting("ntfy_token")
    return NtfyClient(topic=topic, server=server, auth=token or None)


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
    _client().send(
        message=msg,
        title=f"📉 {product_title}",
        priority=MessagePriority.DEFAULT,
        tags=["shopping", "boardgame"],
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
    _client().send(
        message=f"{price:.0f}  ·  {store_name}",
        title=f"✅ Back in stock: {product_title}",
        priority=MessagePriority.HIGH,
        tags=["shopping", "boardgame"],
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
    _client().send(
        message=f"Target {target_price:.0f} hit — now {current_price:.0f}\n{store_name}",
        title=f"🎯 Price target hit: {product_title}",
        priority=MessagePriority.HIGH,
        tags=["shopping", "boardgame"],
        actions=actions,
    )
