from abc import ABC, abstractmethod


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
