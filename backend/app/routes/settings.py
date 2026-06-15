import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_all_settings, get_setting, set_setting
from ..logger import get_logger

router = APIRouter(prefix="/settings", tags=["settings"])
log = get_logger(__name__)

KEYS = ["bgg_api_token", "ntfy_server", "ntfy_topic", "ntfy_token"]


class SettingsUpdate(BaseModel):
    bgg_api_token: str = ""
    ntfy_server: str = ""
    ntfy_topic: str = ""
    ntfy_token: str = ""


@router.get("/")
def read_settings():
    data = get_all_settings()
    # Mask token — send presence flag, not value
    data["bgg_api_token"] = "****" if data.get("bgg_api_token") else ""
    data["ntfy_token"] = "****" if data.get("ntfy_token") else ""
    return data


@router.put("/")
def update_settings(body: SettingsUpdate):
    changed = []
    for key in KEYS:
        val = getattr(body, key, "")
        # Ignore placeholder sent back from UI
        if val and val != "****":
            set_setting(key, val)
            changed.append(key)
    # Log which keys changed — never the values (tokens are secret).
    log.info("settings updated: %s", ", ".join(changed) or "none")
    return {"ok": True}


@router.post("/test/bgg")
async def test_bgg():
    token = get_setting("bgg_api_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://boardgamegeek.com/xmlapi2/thing",
                params={"id": "13"},
                headers=headers,
            )
        if r.status_code == 200:
            return {"ok": True, "message": "BGG API reachable and token valid"}
        if r.status_code == 401:
            return {
                "ok": False,
                "message": "Token rejected (401). Register at boardgamegeek.com/using_the_xml_api",
            }
        return {"ok": False, "message": f"Unexpected status {r.status_code}"}
    except Exception as e:
        log.warning("bgg test failed: %s", e)
        return {"ok": False, "message": str(e)}


@router.post("/test/ntfy")
async def test_ntfy():
    from ..notifier import _client

    try:
        _client().send(
            message="Test notification from Board Game Tracker ✓",
            title="Connection test",
            tags=["white_check_mark"],
        )
        log.info("ntfy test notification sent")
        return {"ok": True, "message": "Notification sent — check your ntfy app"}
    except Exception as e:
        log.warning("ntfy test failed: %s", e)
        return {"ok": False, "message": str(e)}
