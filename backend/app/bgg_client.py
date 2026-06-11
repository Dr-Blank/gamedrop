import asyncio
import json
from datetime import datetime, timedelta

import httpx
import xmltodict
from sqlmodel import Session

from .config import get_setting
from .db import engine
from .models import BggCache

BGG_API = "https://boardgamegeek.com/xmlapi2"
CACHE_TTL_HOURS = 24

# Semaphore: max 1 concurrent BGG request + 1.1s gap (conservative, avoids bans).
_bgg_lock = asyncio.Semaphore(1)
_BGG_MIN_INTERVAL = 1.1
_last_request_at: float = 0.0


def _auth_headers() -> dict:
    token = get_setting("bgg_api_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _xml_get(path: str, params: dict = {}) -> dict:
    global _last_request_at
    async with _bgg_lock:
        now = asyncio.get_event_loop().time()
        wait = _BGG_MIN_INTERVAL - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)

        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(5):
                r = await client.get(
                    f"{BGG_API}{path}",
                    params=params,
                    headers=_auth_headers(),
                )
                _last_request_at = asyncio.get_event_loop().time()
                if r.status_code == 202:
                    await asyncio.sleep(3)
                    continue
                r.raise_for_status()
                return xmltodict.parse(r.text)
    raise RuntimeError("BGG API not ready after retries")


async def search_games(query: str) -> list[dict]:
    data = await _xml_get("/search", {"query": query, "type": "boardgame"})
    items = data.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    results = []
    for item in items:
        name = item.get("name", {})
        results.append({
            "bgg_id": int(item["@id"]),
            "name": name.get("@value", "") if isinstance(name, dict) else "",
            "year": item.get("yearpublished", {}).get("@value") if isinstance(item.get("yearpublished"), dict) else None,
        })
    return results


async def get_game(bgg_id: int) -> dict:
    with Session(engine) as session:
        cached = session.get(BggCache, bgg_id)
        if cached:
            age = datetime.utcnow() - cached.cached_at
            if age < timedelta(hours=CACHE_TTL_HOURS):
                return json.loads(cached.data)

    data = await _xml_get("/thing", {"id": bgg_id, "stats": 1})
    item = data.get("items", {}).get("item", {})
    if isinstance(item, list):
        item = item[0]

    names = item.get("name", [])
    if isinstance(names, dict):
        names = [names]
    primary_name = next((n["@value"] for n in names if n.get("@type") == "primary"), "")

    stats = item.get("statistics", {}).get("ratings", {})

    result = {
        "bgg_id": bgg_id,
        "name": primary_name,
        "year": item.get("yearpublished", {}).get("@value"),
        "thumbnail": item.get("thumbnail"),
        "image": item.get("image"),
        "description": item.get("description", "")[:500],
        "min_players": item.get("minplayers", {}).get("@value"),
        "max_players": item.get("maxplayers", {}).get("@value"),
        "min_playtime": item.get("minplaytime", {}).get("@value"),
        "max_playtime": item.get("maxplaytime", {}).get("@value"),
        "min_age": item.get("minage", {}).get("@value"),
        "avg_rating": stats.get("average", {}).get("@value"),
        "bgg_rating": stats.get("bayesaverage", {}).get("@value"),
        "num_votes": stats.get("usersrated", {}).get("@value"),
        "avg_weight": stats.get("averageweight", {}).get("@value"),
        "rank": None,
        "bgg_url": f"https://boardgamegeek.com/boardgame/{bgg_id}",
    }

    ranks = stats.get("ranks", {}).get("rank", [])
    if isinstance(ranks, dict):
        ranks = [ranks]
    for rank in ranks:
        if rank.get("@name") == "boardgame":
            try:
                result["rank"] = int(rank["@value"])
            except (ValueError, TypeError):
                pass

    with Session(engine) as session:
        cached = session.get(BggCache, bgg_id)
        if cached:
            cached.data = json.dumps(result)
            cached.cached_at = datetime.utcnow()
        else:
            cached = BggCache(bgg_id=bgg_id, data=json.dumps(result))
            session.add(cached)
        session.commit()

    return result
