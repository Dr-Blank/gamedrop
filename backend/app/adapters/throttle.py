"""Backing off from shops that push back, without holding up the others."""

import asyncio
import time

import httpx

MAX_WAIT_SEC = 900
FIRST_BLOCK_SEC = 3600
#: Below the default sync interval, so a block can't swallow every scheduled sync.
MAX_BLOCK_SEC = 12 * 3600
RATE_LIMITED_PREFIX = "rate limited by shop"


def retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["retry-after"]), MAX_WAIT_SEC)
    except (KeyError, ValueError):
        return None


def _rounded(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"{round(minutes / 60)}h" if minutes >= 60 else f"{minutes}m"


class ShopRateLimited(Exception):
    """A shop keeps refusing this client, so retrying soon won't help."""

    def __init__(self, seconds: float) -> None:
        super().__init__(f"{RATE_LIMITED_PREFIX}, next try in {_rounded(seconds)}")


class RequestGate:
    """Spaces requests across shops, and holds back only the shop that refused."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._ready_at = 0.0
        self._paused_until: dict[str, float] = {}
        self._blocked_until: dict[str, float] = {}
        self._blocks: dict[str, int] = {}

    def pause(self, shop: str, seconds: float) -> None:
        until = max(self._paused_until.get(shop, 0), time.monotonic() + seconds)
        self._paused_until[shop] = until

    def block(self, shop: str) -> ShopRateLimited:
        """Stop asking this shop for a stretch that grows with each block in a row."""
        blocks = self._blocks.get(shop, 0)
        seconds = min(FIRST_BLOCK_SEC * 2**blocks, MAX_BLOCK_SEC)
        self._blocks[shop] = blocks + 1
        self._blocked_until[shop] = time.monotonic() + seconds
        return ShopRateLimited(seconds)

    def clear(self, shop: str) -> None:
        self._paused_until.pop(shop, None)
        self._blocked_until.pop(shop, None)
        self._blocks.pop(shop, None)

    async def wait(self, shop: str, gap: float) -> None:
        while True:
            left = self._blocked_until.get(shop, 0) - time.monotonic()
            if left > 0:
                raise ShopRateLimited(left)
            while (left := self._paused_until.get(shop, 0) - time.monotonic()) > 0:
                await asyncio.sleep(left)
            async with self._lock:
                while (left := self._ready_at - time.monotonic()) > 0:
                    await asyncio.sleep(left)
                now = time.monotonic()
                # Looped because a refusal can land while this request queues.
                if (
                    self._paused_until.get(shop, 0) <= now
                    and self._blocked_until.get(shop, 0) <= now
                ):
                    self._ready_at = now + gap
                    return
