from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()  # must run before app modules that read os.environ

from app.db import create_db  # noqa: E402
from app.routes import (  # noqa: E402
    bgg,
    browse,
    prices,
    settings,
    stores,
    watchlist,
)
from app.scheduler import start_scheduler  # noqa: E402
from app.scraper import sync_all_stores  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db()
    start_scheduler(sync_all_stores)
    yield


app = FastAPI(title="Board Game Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stores.router, prefix="/api")
app.include_router(bgg.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(browse.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve SvelteKit SPA — must be last so /api routes take priority
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
