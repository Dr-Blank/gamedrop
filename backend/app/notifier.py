from datetime import datetime

from .channels import DatabaseChannel, NotificationChannel, NtfyChannel
from .logger import get_logger

log = get_logger(__name__)


def _channels() -> list[NotificationChannel]:
    return [NtfyChannel(), DatabaseChannel()]


def _dispatch(
    channels: list[NotificationChannel],
    *,
    kind: str,
    title: str,
    message: str,
    product_id: int | None,
    url: str | None,
    game_id: int | None = None,
    tags: list[str],
    recorded_at: datetime | None = None,
) -> None:
    for ch in channels:
        try:
            ch.send(
                kind=kind,
                title=title,
                message=message,
                product_id=product_id,
                game_id=game_id,
                url=url,
                tags=tags,
                recorded_at=recorded_at,
            )
            log.info(
                "notification sent via %s: %s",
                type(ch).__name__,
                kind,
                extra={"channel": type(ch).__name__, "kind": kind},
            )
        except Exception:
            log.exception(
                "channel failed: %s kind=%s",
                type(ch).__name__,
                kind,
                extra={"channel": type(ch).__name__, "kind": kind},
            )


def notify_price_drop(
    product_title: str,
    old_price: float,
    new_price: float,
    product_url: str | None,
    store_name: str,
    product_id: int | None = None,
    game_id: int | None = None,
    channels: list[NotificationChannel] | None = None,
    recorded_at: datetime | None = None,
):
    pct = round((old_price - new_price) / old_price * 100)
    _dispatch(
        channels if channels is not None else _channels(),
        kind="price_drop",
        title=f"Price drop: {product_title}",
        message=f"{old_price:.0f} → {new_price:.0f}  ({pct}% off)\n{store_name}",
        product_id=product_id,
        game_id=game_id,
        url=product_url,
        tags=["chart_with_downwards_trend", "shopping"],
        recorded_at=recorded_at,
    )


def notify_back_in_stock(
    product_title: str,
    price: float,
    product_url: str | None,
    store_name: str,
    product_id: int | None = None,
    game_id: int | None = None,
    channels: list[NotificationChannel] | None = None,
    recorded_at: datetime | None = None,
):
    _dispatch(
        channels if channels is not None else _channels(),
        kind="back_in_stock",
        title=f"Back in stock: {product_title}",
        message=f"{price:.0f}  ·  {store_name}",
        product_id=product_id,
        game_id=game_id,
        url=product_url,
        tags=["white_check_mark", "shopping"],
        recorded_at=recorded_at,
    )


def notify_target_reached(
    product_title: str,
    target_price: float,
    current_price: float,
    product_url: str | None,
    store_name: str,
    product_id: int | None = None,
    game_id: int | None = None,
    channels: list[NotificationChannel] | None = None,
    recorded_at: datetime | None = None,
):
    _dispatch(
        channels if channels is not None else _channels(),
        kind="target_reached",
        title=f"Price target hit: {product_title}",
        message=f"Target {target_price:.0f} hit — now {current_price:.0f}\n{store_name}",
        product_id=product_id,
        game_id=game_id,
        url=product_url,
        tags=["dart", "shopping"],
        recorded_at=recorded_at,
    )


def notify_out_of_stock(
    product_title: str,
    price: float,
    product_url: str | None,
    store_name: str,
    product_id: int | None = None,
    game_id: int | None = None,
    channels: list[NotificationChannel] | None = None,
    recorded_at: datetime | None = None,
):
    _dispatch(
        channels if channels is not None else _channels(),
        kind="out_of_stock",
        title=f"Out of stock: {product_title}",
        message=f"Was {price:.0f}  ·  {store_name}",
        product_id=product_id,
        game_id=game_id,
        url=product_url,
        tags=["x", "shopping"],
        recorded_at=recorded_at,
    )


def notify_price_increase(
    product_title: str,
    old_price: float,
    new_price: float,
    product_url: str | None,
    store_name: str,
    product_id: int | None = None,
    game_id: int | None = None,
    channels: list[NotificationChannel] | None = None,
    recorded_at: datetime | None = None,
):
    pct = round((new_price - old_price) / old_price * 100)
    _dispatch(
        channels if channels is not None else _channels(),
        kind="price_increase",
        title=f"Price increased: {product_title}",
        message=f"{old_price:.0f} → {new_price:.0f}  (+{pct}%)\n{store_name}",
        product_id=product_id,
        game_id=game_id,
        url=product_url,
        tags=["chart_with_upwards_trend", "shopping"],
        recorded_at=recorded_at,
    )
