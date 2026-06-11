"""
Settings resolution order: DB (set via UI) > environment variable > default.
This lets users configure everything through the UI while still supporting
headless/Docker deployments via env vars or .env file.
"""

import os
from datetime import datetime

from sqlmodel import Session

from .db import engine
from .models import AppSetting

# Maps setting key → environment variable name
_ENV_MAP = {
    "bgg_api_token": "BGG_API_TOKEN",
    "ntfy_server": "NTFY_SERVER",
    "ntfy_topic": "NTFY_TOPIC",
    "ntfy_token": "NTFY_TOKEN",
}

_DEFAULTS = {
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "board-game-tracker",
}


def get_setting(key: str) -> str:
    try:
        with Session(engine) as session:
            s = session.get(AppSetting, key)
            if s and s.value.strip():
                return s.value
    except Exception:
        pass
    env_key = _ENV_MAP.get(key, key.upper())
    return os.environ.get(env_key, _DEFAULTS.get(key, ""))


def set_setting(key: str, value: str) -> None:
    with Session(engine) as session:
        s = session.get(AppSetting, key)
        if s:
            s.value = value
            s.updated_at = datetime.utcnow()
        else:
            s = AppSetting(key=key, value=value)
        session.add(s)
        session.commit()


def get_all_settings() -> dict:
    keys = list(_ENV_MAP.keys())
    return {k: get_setting(k) for k in keys}
