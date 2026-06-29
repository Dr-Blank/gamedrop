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
        url: str | None,
        tags: list[str],
        recorded_at: datetime | None = None,
    ) -> None: ...
