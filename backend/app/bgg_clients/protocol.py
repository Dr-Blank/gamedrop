from typing import Protocol, runtime_checkable


@runtime_checkable
class BggClientProtocol(Protocol):
    async def search(self, query: str) -> list[dict]:
        """Search BGG for games by name. Returns list of {bgg_id, name, year}."""
        ...

    async def get_game(self, bgg_id: int, force: bool = False) -> dict:
        """Fetch full game data. Implementations should cache results permanently.
        Pass force=True to re-fetch even if cached."""
        ...
