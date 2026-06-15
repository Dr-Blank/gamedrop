"""
App-wide structured logging.

Usage:
    from app.logger import get_logger
    log = get_logger(__name__)
    log.info("thing happened", extra={"store_id": "foo"})

Ring buffer retains the last LOG_BUFFER_SIZE records in memory so
GET /api/logs can return them without touching disk.
"""

import logging
import logging.handlers
import platform
import sys
import traceback
from collections import deque
from datetime import UTC, datetime
from typing import Any

LOG_BUFFER_SIZE = 2000


class _StructuredRecord:
    __slots__ = ("ts", "level", "logger", "msg", "extra", "exc")

    def __init__(
        self,
        ts: str,
        level: str,
        logger: str,
        msg: str,
        extra: dict,
        exc: str | None,
    ):
        self.ts = ts
        self.level = level
        self.logger = logger
        self.msg = msg
        self.extra = extra
        self.exc = exc

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "ts": self.ts,
            "level": self.level,
            "logger": self.logger,
            "msg": self.msg,
        }
        if self.extra:
            d["extra"] = self.extra
        if self.exc:
            d["exc"] = self.exc
        return d


class RingBufferHandler(logging.Handler):
    """Thread-safe in-memory ring buffer — no I/O, no blocking."""

    def __init__(self, capacity: int = LOG_BUFFER_SIZE) -> None:
        super().__init__()
        self._buf: deque[_StructuredRecord] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            extra = {
                k: v
                for k, v in record.__dict__.items()
                if k
                not in {
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "taskName",
                    "message",
                }
            }
            exc_text = None
            if record.exc_info:
                exc_text = "".join(traceback.format_exception(*record.exc_info))

            self._buf.append(
                _StructuredRecord(
                    ts=datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                    level=record.levelname,
                    logger=record.name,
                    msg=record.getMessage(),
                    extra=extra,
                    exc=exc_text,
                )
            )
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def records(self, level: str | None = None, limit: int = 200) -> list[dict]:
        buf = list(self._buf)
        if level:
            lvl = level.upper()
            buf = [r for r in buf if r.level == lvl]
        return [r.to_dict() for r in buf[-limit:]]

    def clear(self) -> None:
        self._buf.clear()


_ring: RingBufferHandler | None = None


def setup_logging(level: int = logging.INFO) -> None:
    global _ring
    fmt = logging.Formatter("%(levelname)s  %(name)s  %(message)s")
    _ring = RingBufferHandler()
    _ring.setFormatter(fmt)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(_ring)
    root.addHandler(stream)

    # quieten noisy libs
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_records(level: str | None = None, limit: int = 200) -> list[dict]:
    if _ring is None:
        return []
    return _ring.records(level=level, limit=limit)


def format_github_issue(records: list[dict]) -> str:
    lines = [
        "## Bug Report — Application Logs",
        "",
        f"**Python**: {sys.version}",
        f"**Platform**: {platform.platform()}",
        f"**Generated**: {datetime.now(tz=UTC).isoformat()}",
        "",
        "### Log records",
        "",
        "```",
    ]
    for r in records:
        lines.append(f"[{r['ts']}] {r['level']:8s} {r['logger']}: {r['msg']}")
        if r.get("exc"):
            for ln in r["exc"].splitlines():
                lines.append(f"  {ln}")
    lines.append("```")
    return "\n".join(lines)
