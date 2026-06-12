"""Shared BGG XML fetching + caching utilities used by both client implementations."""

import asyncio
import contextlib
import json
import random
from datetime import datetime

import httpx
import xmltodict
from sqlmodel import Session

from ..db import engine
from ..models import BggCache

BGG_API = "https://boardgamegeek.com/xmlapi2"

_bgg_lock = asyncio.Semaphore(1)
_last_request_at: float = 0.0


async def _xml_get(
    path: str, params: dict, headers: dict, min_gap: float, max_gap: float
) -> dict:
    global _last_request_at
    async with _bgg_lock:
        elapsed = asyncio.get_event_loop().time() - _last_request_at
        delay = random.uniform(min_gap, max_gap) - elapsed
        if delay > 0:
            await asyncio.sleep(delay)

        async with httpx.AsyncClient(timeout=30) as client:
            for _attempt in range(5):
                r = await client.get(f"{BGG_API}{path}", params=params, headers=headers)
                _last_request_at = asyncio.get_event_loop().time()
                if r.status_code == 202:
                    await asyncio.sleep(3)
                    continue
                r.raise_for_status()
                return xmltodict.parse(r.text)
    raise RuntimeError("BGG API not ready after retries")


def _parse_game(data: dict, bgg_id: int) -> dict:
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
            with contextlib.suppress(ValueError, TypeError):
                result["rank"] = int(rank["@value"])
    return result


def _parse_search(data: dict) -> list[dict]:
    items = data.get("items", {}).get("item", [])
    if isinstance(items, dict):
        items = [items]
    results = []
    for item in items:
        name = item.get("name", {})
        results.append(
            {
                "bgg_id": int(item["@id"]),
                "name": name.get("@value", "") if isinstance(name, dict) else "",
                "year": item.get("yearpublished", {}).get("@value")
                if isinstance(item.get("yearpublished"), dict)
                else None,
            }
        )
    return results


def _cache_get(bgg_id: int) -> dict | None:
    with Session(engine) as session:
        cached = session.get(BggCache, bgg_id)
        if cached:
            return json.loads(cached.data)
    return None


def _cache_set(bgg_id: int, data: dict) -> None:
    with Session(engine) as session:
        cached = session.get(BggCache, bgg_id)
        if cached:
            cached.data = json.dumps(data)
            cached.cached_at = datetime.utcnow()
        else:
            session.add(BggCache(bgg_id=bgg_id, data=json.dumps(data)))
        session.commit()
