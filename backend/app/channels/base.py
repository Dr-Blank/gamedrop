from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationChannel(Protocol):
    def send(
        self,
        *,
        kind: str,
        title: str,
        message: str,
        product_id: int | None,
        game_id: int | None = None,
        url: str | None = None,
        tags: list[str] | None = None,
        recorded_at: datetime | None = None,
    ) -> None: ...
