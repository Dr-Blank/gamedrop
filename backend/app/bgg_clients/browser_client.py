"""BGG anonymous browser client — no API key required.

Throttle: 30–300s random gap per request to avoid IP bans.
Cache: permanent (ratings/weight rarely change; force=True to re-fetch).

Use only as fallback when no API key is configured.
"""

from .base import _cache_get, _cache_set, _parse_game, _parse_search, _xml_get

_ANON_MIN = 30.0  # 30 seconds minimum — BGG bans aggressive anonymous scrapers
_ANON_MAX = 300.0  # up to 5 minutes

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class BggBrowserClient:
    async def _get(self, path: str, params: dict) -> dict:
        return await _xml_get(path, params, _BROWSER_HEADERS, _ANON_MIN, _ANON_MAX)

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
