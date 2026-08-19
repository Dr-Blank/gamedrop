# Stage 1: build frontend
FROM node:22-slim AS frontend-builder
WORKDIR /frontend
RUN npm install -g bun@1.3.14
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# Stage 2: backend + serve frontend static files
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# tzdata so the TZ env var resolves named zones, not just fixed offsets
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./
COPY --from=frontend-builder /frontend/build ./static

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
