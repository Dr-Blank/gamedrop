from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()  # must run before app modules that read os.environ

from app.db import run_migrations  # noqa: E402
from app.logger import get_logger, setup_logging  # noqa: E402
from app.routes import (  # noqa: E402
    bgg,
    browse,
    prices,
    settings,
    stores,
    watchlist,
)
from app.routes.applogs import router as applogs_router  # noqa: E402
from app.routes.products import router as products_router  # noqa: E402
from app.scheduler import start_scheduler  # noqa: E402
from app.scraper import sync_all_stores  # noqa: E402

setup_logging()
log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("startup: running migrations")
    run_migrations()
    log.info("startup: starting scheduler")
    start_scheduler(sync_all_stores)
    log.info("startup: ready")
    yield
    log.info("shutdown")


app = FastAPI(title="Board Game Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(stores.router, prefix="/api")
app.include_router(bgg.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(browse.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(applogs_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve SvelteKit SPA — must be last so /api routes take priority
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
