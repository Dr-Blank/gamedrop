from abc import ABC, abstractmethod


class StoreAdapter(ABC):
    def __init__(self, store):
        self.store = store

    @abstractmethod
    async def fetch_products(self) -> list[dict]:
        """Return list of dicts with keys: external_id, title, handle, url, variants"""
        ...
