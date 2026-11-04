"""Backing off from shops that push back, alone or as a whole platform."""

import asyncio
import time

import httpx

MAX_WAIT_SEC = 900


def retry_after(response: httpx.Response) -> float | None:
    try:
        return min(float(response.headers["retry-after"]), MAX_WAIT_SEC)
    except (KeyError, ValueError):
        return None


class RequestGate:
    """Spaces requests across shops, and holds them all while one is told to wait."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._ready_at = 0.0

    def pause(self, seconds: float) -> None:
        self._ready_at = max(self._ready_at, time.monotonic() + seconds)

    async def wait(self, gap: float) -> None:
        async with self._lock:
            # Looped because a pause can land while this request sleeps.
            while (left := self._ready_at - time.monotonic()) > 0:
                await asyncio.sleep(left)
            self._ready_at = time.monotonic() + gap
