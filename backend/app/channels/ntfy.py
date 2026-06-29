from datetime import datetime

from python_ntfy import MessagePriority, NtfyClient, ViewAction

from ..config import get_setting
from ..logger import get_logger

log = get_logger(__name__)

_HIGH_PRIORITY_KINDS = {"back_in_stock", "target_reached"}


def _latin1_safe(text: str) -> str:
    return text.encode("latin-1", "ignore").decode("latin-1")


class NtfyChannel:
    def _client(self) -> NtfyClient:
        server = get_setting("ntfy_server") or "https://ntfy.sh"
        topic = get_setting("ntfy_topic") or "board-game-tracker"
        token = get_setting("ntfy_token")
        return NtfyClient(topic=topic, server=server, auth=token or None)

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
    ) -> None:
        priority = (
            MessagePriority.HIGH
            if kind in _HIGH_PRIORITY_KINDS
            else MessagePriority.DEFAULT
        )
        actions = [ViewAction(label="View on store", url=url)] if url else None
        self._client().send(
            title=_latin1_safe(title),
            message=message,
            priority=priority,
            tags=tags,
            actions=actions,
        )
