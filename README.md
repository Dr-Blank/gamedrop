# GameDrop

Self-hostable price tracker for board game buyers. Add any Shopify store, track prices and stock, get push notifications on price drops and back-in-stock events. Optional BGG integration shows ratings and game info alongside store prices.

## Quick Start

```yaml
services:
  gamedrop:
    image: ghcr.io/dr-blank/gamedrop:latest
    restart: unless-stopped
    ports:
      - "8765:8000"
    volumes:
      - ./gamedrop-data:/data
```

```bash
docker compose up -d
```

Open **http://localhost:8765** — configure BGG token and notifications at `/settings`.

---

## Features

- **BGG game page** — shows price, stock, and store link for any tracked store
- **Store product page** — shows BGG rating, rank, weight, player count
- **Browse** — filter all scraped products by store, price range, stock, BGG rating
- **Price history** — chart of price over time per product
- **Watchlist** — track games with optional target price
- **Push notifications** — ntfy alerts for price drops, target hit, back in stock
- **Web UI** — manage stores, settings, watchlist without touching config files
- **Any Shopify store** — add any Shopify store via URL; non-Shopify supported via custom adapter

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, SQLite |
| Package manager (backend) | uv |
| Frontend | SvelteKit (static SPA), Tailwind CSS v4, shadcn-svelte |
| Package manager (frontend) | Bun |
| HTTP client | httpx (async) |
| Scheduler | APScheduler |
| BGG data | BGG XML API2 (bearer token required) |
| Notifications | ntfy (self-hosted or ntfy.sh) |
| Container | Docker (single image, GHCR) |
| Userscript | Violentmonkey (Firefox) |

---

## Development

### Requirements

- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) (or Node 22+)

### 1. Backend

```bash
cd backend
cp .env.example .env   # add BGG_API_TOKEN (see below)
uv sync
uv run uvicorn main:app --reload --port 8765
```

API docs: **http://localhost:8765/docs**

### 2. Frontend

```bash
cd frontend
bun install
bun run dev            # starts on http://localhost:5173
```

Vite proxies all `/api` requests to the backend on `:8765` automatically — no CORS config needed during dev.

### VS Code (recommended)

| Action | How |
|---|---|
| **Start both** | `Ctrl+Shift+B` → `Dev: Both` — parallel panels |
| Start backend only | Terminal → Run Task → `Dev: Backend` |
| Start frontend only | Terminal → Run Task → `Dev: Frontend` |
| Debug with breakpoints | `F5` → `Backend: Debug (uvicorn)` |
| Sync all stores | Terminal → Run Task → `Store: Sync all` |
| Health check | Terminal → Run Task → `Backend: Health check` |

> **VS Code Python import errors**: Press `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv` inside `backend/`. The `settings.json` already points to it; a reload may be needed.

---

## Production (Docker / Dockge)

One container, one port. The Docker image bundles the SvelteKit SPA — FastAPI serves both the API and frontend.

```
Container (port 8000)
  └── FastAPI
        ├── /api/*   → backend logic
        └── /*       → SvelteKit SPA (static)
```

### Deploy

1. Save the compose snippet from [Quick Start](#quick-start) as `docker-compose.yml`
2. `docker compose up -d`
3. Open **http://\<host\>:8765** and configure everything at `/settings`

Data persists in `./gamedrop-data` across restarts and updates.

### Nginx reverse proxy

```nginx
location / {
    proxy_pass http://<host-ip>:8765;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Update `api_base` in the userscript to your public URL (e.g. `https://bgg.example.com/api`).

---

## First-time configuration

### BGG API token

BGG requires a registered bearer token (required since October 2025).

1. Log in at boardgamegeek.com
2. Go to **https://boardgamegeek.com/using_the_xml_api**
3. Register your application and copy the token
4. Paste it in the web UI at `/settings` **or** add to `backend/.env`:
   ```
   BGG_API_TOKEN=your_token_here
   ```

UI settings take priority over env vars if both are set.

### Push notifications (ntfy)

Optional. Works with [ntfy.sh](https://ntfy.sh) or self-hosted ntfy.

Configure via the web UI at `/settings → Push notifications` or via env vars:
```
NTFY_SERVER=https://ntfy.sh
NTFY_TOPIC=board-game-tracker
NTFY_TOKEN=                    # leave blank if no auth required
```

Use **Send test notification** in the UI to verify it works.

---

## Adding stores

### Via the web UI (easiest)

Open `/stores` → **Add store**:

| Field | Example |
|---|---|
| ID | `my-store` (lowercase, no spaces) |
| Name | `My Store` |
| Type | `shopify` |
| Base URL | `https://mystore.com` |
| Collection path | `/collections/board-games` |

After adding, click **Sync now** or **Sync all stores** to scrape products and prices.

### Via curl

```bash
curl -X POST http://localhost:8765/api/stores/ \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "my-store",
    "name": "My Store",
    "type": "shopify",
    "base_url": "https://mystore.com",
    "collection_path": "/collections/board-games"
  }'

# trigger first sync
curl -X POST http://localhost:8765/api/stores/my-store/sync

# sync all stores at once
curl -X POST http://localhost:8765/api/stores/sync-all
```

### Scrape config

Per-store settings (editable in the UI under each store row):

| Setting | Default | Description |
|---|---|---|
| Timeout | 30s | HTTP request timeout per page |
| Delay between pages | 1s | Sleep between paginated requests |
| Sync interval | 6h | How often APScheduler re-syncs |

### Non-Shopify stores

1. Create `backend/app/adapters/my_store.py`:

```python
from .base import StoreAdapter

class MyStoreAdapter(StoreAdapter):
    async def fetch_products(self) -> list[dict]:
        # Return a list of dicts:
        # {
        #   external_id: str,
        #   title: str,
        #   url: str | None,
        #   handle: str | None,
        #   variants: [{ variant_id, variant_title, price, compare_at_price, available }]
        # }
        ...
```

2. Register it in `backend/app/scraper.py` → `get_adapter()`:

```python
elif store.type == "my_store":
    return MyStoreAdapter(store)
```

3. Add the store via the UI or API with `"type": "my_store"`.

---

## Userscript

1. Install [Violentmonkey](https://violentmonkey.github.io/) in Firefox
2. Open `userscript/gamedrop.user.js` — Violentmonkey detects it and prompts install
3. If your backend is not on `localhost:8765`, edit `api_base` in the script header

The script activates on:
- `boardgamegeek.com/boardgame/*` — injects price panel on game pages
- Store product pages — injects BGG rating panel

---

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/stores/` | List all stores |
| POST | `/api/stores/` | Add store |
| PATCH | `/api/stores/{id}` | Update store (name, url, scrape_config, enabled) |
| DELETE | `/api/stores/{id}` | Remove store |
| POST | `/api/stores/sync-all` | Trigger sync on all enabled stores |
| POST | `/api/stores/{id}/sync` | Trigger sync on one store |
| GET | `/api/stores/{id}/products?q=` | Search products in store |
| GET | `/api/bgg/search?q=` | Search BGG by name |
| GET | `/api/bgg/game/{bgg_id}` | BGG game details (cached 24h) |
| POST | `/api/bgg/game/{bgg_id}/link/{product_id}` | Link BGG ID to product |
| GET | `/api/prices/product/{id}` | Price history for a product |
| GET | `/api/prices/search?q=&store_id=` | Search products with latest price |
| GET | `/api/watchlist/` | List watchlist items |
| POST | `/api/watchlist/` | Add to watchlist |
| PATCH | `/api/watchlist/{id}` | Update target price |
| DELETE | `/api/watchlist/{id}` | Remove from watchlist |
| GET | `/api/browse?...` | Browse all products with filters |
| GET | `/api/browse/stores` | List stores for browse filter |
| GET | `/api/settings/` | Get config (tokens masked) |
| PUT | `/api/settings/` | Save config |
| POST | `/api/settings/test/bgg` | Test BGG connection |
| POST | `/api/settings/test/ntfy` | Send test notification |

---

## Database schema

| Table | Purpose |
|---|---|
| `store` | Configured stores |
| `product` | Scraped products; `bgg_id` null until linked |
| `pricesnapshot` | Append-only price history — one row per change |
| `bggcache` | BGG game JSON cached for 24h |
| `watchlistitem` | Watched products with optional target price |
| `appsetting` | Key-value config (overrides env vars) |

SQLite file: `backend/data/tracker.db` (local) or `/data/tracker.db` (Docker volume).

---

## BGG rate limiting

BGG client enforces a minimum 1.1s gap between requests and processes one at a time via asyncio semaphore. BGG data is cached 24h. Keeps request rates well within BGG's limits.

---

## Publishing to GHCR

Push to `main` or a version tag — the GitHub Actions workflow in `.github/workflows/docker.yml` builds and pushes automatically:

```bash
git tag v1.0.0
git push origin v1.0.0
# → ghcr.io/dr-blank/gamedrop:1.0.0
# → ghcr.io/dr-blank/gamedrop:latest
```

---

## Roadmap

- [ ] BGG collection list view — inline price column per row
- [ ] Store collection page — BGG rating badge on each game card
- [ ] Price drop browser notifications (`GM_notification`)
- [ ] Fuzzy matching for automatic BGG ↔ product linking
- [ ] Admin UI for manual BGG ID ↔ product correction
