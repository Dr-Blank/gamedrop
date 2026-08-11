import json
from abc import ABC, abstractmethod

_DEFAULTS = {"timeout_sec": 30, "request_delay_sec": 1, "sync_interval_hours": 6}


def store_cfg(store, key):
    """Read one key out of a store's `scrape_config` JSON, falling back to the
    shared default. Bad JSON is treated as "no config" rather than an error —
    the config is user-editable text, and a typo shouldn't break syncing."""
    try:
        return json.loads(store.scrape_config).get(key, _DEFAULTS[key])
    except Exception:
        return _DEFAULTS[key]


class StoreAdapter(ABC):
    def __init__(self, store):
        self.store = store

    @abstractmethod
    async def fetch_products(self) -> list[dict]:
        """Return list of dicts with keys: external_id, title, handle, url, variants"""
        ...

    async def fetch_product_image(self, product) -> str | None:
        """Fetch the image URL for a single product on demand. None if unsupported."""
        return None
