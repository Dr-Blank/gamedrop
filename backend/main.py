from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()  # must run before app modules that read os.environ

from app.db import run_migrations  # noqa: E402
from app.logger import get_logger, setup_logging  # noqa: E402
from app.routes import (  # noqa: E402
    bgg,
    browse,
    catalog,
    prices,
    settings,
    stores,
    watchlist,
)
from app.routes.applogs import router as applogs_router  # noqa: E402
from app.routes.notifications import router as notifications_router  # noqa: E402
from app.routes.products import router as products_router  # noqa: E402
from app.routes.shelves import router as shelves_router  # noqa: E402
from app.scheduler import start_scheduler  # noqa: E402
from app.scraper import sync_all_stores  # noqa: E402

setup_logging()
log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _seed_shelves():
    """Insert built-in shelves if they don't exist yet (idempotent)."""
    import json

    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Shelf

    def _f(*conditions):
        """Build an AND group from condition dicts."""
        if len(conditions) == 1:
            return json.dumps(
                {"type": "group", "op": "and", "conditions": [conditions[0]]}
            )
        return json.dumps(
            {"type": "group", "op": "and", "conditions": list(conditions)}
        )

    def _c(field, op, value):
        return {"type": "condition", "field": field, "op": op, "value": value}

    def _s(*pairs):
        return json.dumps([{"field": f, "dir": d} for f, d in pairs])

    BUILT_INS = [
        # ── Discovery & browsing ──────────────────────────────────────────────
        {
            "name": "Surprise Me",
            "icon": "Zap",
            "filters": _f(_c("available", "eq", True)),
            "sorts": _s(("random", "asc")),
            "position": 0,
        },
        {
            "name": "New Arrivals",
            "icon": "Sparkles",
            "filters": None,
            "sorts": _s(("first_seen", "desc")),
            "position": 1,
        },
        {
            "name": "Not in Watchlist",
            "icon": "Compass",
            "filters": _f(
                _c("available", "eq", True),
                _c("is_watched", "eq", False),
                _c("bgg_rating", "is_not_null", None),
            ),
            "sorts": _s(("bgg_rating", "desc")),
            "position": 2,
        },
        # ── Price & deals ────────────────────────────────────────────────────
        {
            "name": "Price Drops",
            "icon": "TrendingDown",
            "filters": _f(_c("price_change", "lt", 0)),
            "sorts": _s(("price_change", "asc"), ("recorded_at", "desc")),
            "position": 3,
        },
        {
            "name": "Top Discounts",
            "icon": "Tag",
            "filters": _f(_c("discount_pct", "gt", 0), _c("available", "eq", True)),
            "sorts": _s(("discount_pct", "desc")),
            "position": 4,
        },
        {
            "name": "Steep Deals",
            "icon": "TrendingDown",
            "filters": _f(_c("discount_pct", "gte", 30), _c("available", "eq", True)),
            "sorts": _s(("discount_abs", "desc")),
            "position": 5,
        },
        # ── Quality & ratings ────────────────────────────────────────────────
        {
            "name": "Top Rated",
            "icon": "Star",
            "filters": _f(_c("bgg_rating", "gte", 8), _c("available", "eq", True)),
            "sorts": _s(("bgg_rating", "desc")),
            "position": 6,
        },
        {
            "name": "BGG Top 100",
            "icon": "Star",
            "filters": _f(_c("bgg_rank", "lte", 100), _c("available", "eq", True)),
            "sorts": _s(("bgg_rank", "asc")),
            "position": 7,
        },
        {
            "name": "Hidden Gems",
            "icon": "Sparkles",
            "filters": _f(
                _c("bgg_rating", "gte", 7),
                _c("discount_pct", "gt", 0),
                _c("available", "eq", True),
            ),
            "sorts": _s(("discount_pct", "desc"), ("bgg_rating", "desc")),
            "position": 8,
        },
        # ── Complexity tiers ─────────────────────────────────────────────────
        {
            "name": "Gateway Games",
            "icon": "Compass",
            "filters": _f(
                _c("avg_weight", "gte", 1.0),
                _c("avg_weight", "lte", 2.0),
                _c("bgg_rating", "gte", 6.5),
                _c("available", "eq", True),
            ),
            "sorts": _s(("bgg_rating", "desc")),
            "position": 9,
        },
        {
            "name": "Strategy Heavy",
            "icon": "Layers",
            "filters": _f(
                _c("avg_weight", "gte", 3.5),
                _c("bgg_rating", "gte", 7),
                _c("available", "eq", True),
            ),
            "sorts": _s(("avg_weight", "desc"), ("bgg_rating", "desc")),
            "position": 10,
        },
        # ── Watchlist ─────────────────────────────────────────────────────────
        {
            "name": "Your Watchlist",
            "icon": "Heart",
            "filters": _f(_c("is_watched", "eq", True)),
            "sorts": _s(("available", "desc"), ("price", "asc")),
            "position": 11,
        },
        # ── Stock ────────────────────────────────────────────────────────────
        {
            # Was unavailable last snapshot, now available
            "name": "Back in Stock",
            "icon": "Package",
            "filters": _f(_c("back_in_stock", "eq", True)),
            "sorts": _s(("recorded_at", "desc")),
            "position": 12,
        },
        # ── Price increase alerts — buy before it rises more ──────────────────
        {
            # Prices actively going up — biggest jumps first
            "name": "Rising Fast",
            "icon": "TrendingUp",
            "filters": _f(_c("price_change", "gt", 0), _c("available", "eq", True)),
            "sorts": _s(("price_change", "desc")),
            "position": 13,
        },
        {
            # Rising but still has a compare_at discount — window closing
            "name": "Deal Closing Soon",
            "icon": "Zap",
            "filters": _f(
                _c("price_change", "gt", 0),
                _c("discount_pct", "gt", 0),
                _c("available", "eq", True),
            ),
            "sorts": _s(("discount_pct", "asc"), ("price_change", "desc")),
            "position": 14,
        },
        {
            # Rising but still affordable — buy before it crosses ₹1000
            "name": "Affordable & Rising",
            "icon": "TrendingUp",
            "filters": _f(
                _c("price_change", "gt", 0),
                _c("price", "lte", 1000),
                _c("available", "eq", True),
            ),
            "sorts": _s(("price_change", "desc"), ("price", "asc")),
            "position": 15,
        },
        {
            # Price crept back up, barely any discount left vs compare_at
            "name": "Almost Full Price",
            "icon": "TrendingUp",
            "filters": _f(
                _c("price_change", "gt", 0),
                _c("discount_pct", "gt", 0),
                _c("discount_pct", "lte", 10),
                _c("available", "eq", True),
            ),
            "sorts": _s(("discount_pct", "asc")),
            "position": 16,
        },
        {
            # Watched items whose price went up — act or update target
            "name": "Watchlist Price Alert",
            "icon": "Heart",
            "filters": _f(
                _c("is_watched", "eq", True),
                _c("price_change", "gt", 0),
            ),
            "sorts": _s(("price_change", "desc")),
            "position": 17,
        },
    ]
    with Session(engine) as session:
        existing_names = {
            s.name
            for s in session.exec(select(Shelf).where(Shelf.built_in == True)).all()  # noqa: E712
        }
        for spec in BUILT_INS:
            if spec["name"] not in existing_names:
                session.add(Shelf(**spec, built_in=True))
        session.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("startup: running migrations")
    run_migrations()
    log.info("startup: seeding shelves")
    _seed_shelves()
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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time

    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    # Skip static asset noise; keep API + page navigations.
    if request.url.path.startswith("/api"):
        log.info(
            "%s %s -> %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": elapsed_ms,
            },
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(stores.router, prefix="/api")
app.include_router(bgg.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(browse.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(applogs_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(shelves_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve SvelteKit SPA — must be last so /api routes take priority.
# Hashed build assets are mounted; every other non-/api path falls back to
# index.html so client-side routes survive a full reload (F5) / deep link.
if STATIC_DIR.exists():
    app.mount("/_app", StaticFiles(directory=STATIC_DIR / "_app"), name="_app")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
