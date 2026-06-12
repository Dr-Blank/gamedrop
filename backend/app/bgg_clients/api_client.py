"""BGG API client — uses an API key for authenticated requests.

Throttle: 0.5–1.5s random gap (BGG allows higher rate with a key).
Cache: permanent (ratings/weight rarely change; force=True to re-fetch).
"""

from .base import _cache_get, _cache_set, _parse_game, _parse_search, _xml_get

_API_MIN = 0.5
_API_MAX = 1.5


class BggApiClient:
    def __init__(self, api_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {api_token}"}

    async def _get(self, path: str, params: dict) -> dict:
        return await _xml_get(path, params, self._headers, _API_MIN, _API_MAX)

    async def search(self, query: str) -> list[dict]:
        data = await self._get("/search", {"query": query, "type": "boardgame"})
        return _parse_search(data)

    async def get_game(self, bgg_id: int, force: bool = False) -> dict:
        if not force:
            cached = _cache_get(bgg_id)
            if cached:
                return cached
        data = await self._get("/thing", {"id": bgg_id, "stats": 1})
        result = _parse_game(data, bgg_id)
        _cache_set(bgg_id, result)
        return result
