"""Thin compatibility shim — routes import from here; logic lives in bgg_clients/."""

from .bgg_clients import get_bgg_client


async def search_games(query: str) -> list[dict]:
    return await get_bgg_client().search(query)


async def get_game(bgg_id: int, force: bool = False) -> dict:
    return await get_bgg_client().get_game(bgg_id, force=force)
