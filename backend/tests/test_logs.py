"""Tests for GET /api/logs and GET /api/logs/github-issue."""

from fastapi.testclient import TestClient

from app.logger import get_logger, get_records, setup_logging


def _ensure_logging():
    """setup_logging is idempotent but guard against double handler additions in tests."""
    from app.logger import _ring

    if _ring is None:
        setup_logging()


def test_logs_endpoint_returns_list(client: TestClient):
    _ensure_logging()
    r = client.get("/api/logs/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_logs_endpoint_captures_records(client: TestClient):
    _ensure_logging()
    log = get_logger("test.logs")
    log.warning("test warning for unit test")

    r = client.get("/api/logs/?level=WARNING")
    assert r.status_code == 200
    records = r.json()
    msgs = [rec["msg"] for rec in records]
    assert any("test warning for unit test" in m for m in msgs)


def test_logs_endpoint_level_filter(client: TestClient):
    _ensure_logging()
    log = get_logger("test.filter")
    log.debug("a debug line")
    log.error("an error line")

    r = client.get("/api/logs/?level=ERROR")
    assert r.status_code == 200
    for rec in r.json():
        assert rec["level"] == "ERROR"


def test_logs_endpoint_limit(client: TestClient):
    _ensure_logging()
    log = get_logger("test.limit")
    for i in range(20):
        log.info("bulk message %d", i)

    r = client.get("/api/logs/?limit=5")
    assert r.status_code == 200
    assert len(r.json()) <= 5


def test_logs_record_structure(client: TestClient):
    _ensure_logging()
    log = get_logger("test.structure")
    log.error("structured error")

    r = client.get("/api/logs/?level=ERROR")
    assert r.status_code == 200
    records = r.json()
    assert len(records) >= 1
    rec = records[-1]
    assert "ts" in rec
    assert "level" in rec
    assert "logger" in rec
    assert "msg" in rec


def test_logs_captures_exc_info(client: TestClient):
    _ensure_logging()
    log = get_logger("test.exc")
    try:
        raise ValueError("deliberate test error")
    except ValueError:
        log.exception("caught in test")

    r = client.get("/api/logs/?level=ERROR")
    assert r.status_code == 200
    records = r.json()
    exc_records = [rec for rec in records if rec.get("exc")]
    assert len(exc_records) >= 1
    assert "ValueError" in exc_records[-1]["exc"]


def test_github_issue_export_returns_text(client: TestClient):
    _ensure_logging()
    log = get_logger("test.github")
    log.error("export test error")

    r = client.get("/api/logs/github-issue?level=ERROR")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "## Bug Report" in body
    assert "**Python**" in body
    assert "```" in body


def test_github_issue_export_contains_error_records(client: TestClient):
    _ensure_logging()
    log = get_logger("test.github.content")
    log.error("unique export marker xyzzy")

    r = client.get("/api/logs/github-issue?level=ERROR")
    assert "xyzzy" in r.text


def test_github_issue_export_default_includes_non_error_logs(client: TestClient):
    """Regression: export used to default to ERROR, so with no errors it was a
    bare template with an empty ``` ``` block. Default must include all logs."""
    _ensure_logging()
    log = get_logger("test.github.default")
    log.info("info marker plugh")

    r = client.get("/api/logs/github-issue")
    assert r.status_code == 200
    assert "plugh" in r.text
    # The code block must not be empty.
    body = r.text
    block = body.split("```")[1]
    assert block.strip(), "github issue export had an empty log block"


def test_github_issue_export_empty_level_means_all(client: TestClient):
    _ensure_logging()
    log = get_logger("test.github.empty")
    log.info("info marker waldo")

    r = client.get("/api/logs/github-issue?level=")
    assert "waldo" in r.text


def test_get_records_helper_respects_level():
    _ensure_logging()
    log = get_logger("test.helper")
    log.info("info only")
    log.critical("critical only")

    critical = get_records(level="CRITICAL")
    assert all(r["level"] == "CRITICAL" for r in critical)
