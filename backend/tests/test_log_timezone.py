"""Stdout log timestamps follow the TZ env var; buffered records stay absolute."""

import logging
import time

import pytest

from app.logger import LOG_DATE_FORMAT, RingBufferHandler, setup_logging


@pytest.fixture
def restore_tz():
    import os

    original = os.environ.get("TZ")
    yield
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


def _record():
    return logging.LogRecord("t", logging.INFO, "p", 1, "m", None, None)


def _formatted(tz: str) -> str:
    import os

    os.environ["TZ"] = tz
    setup_logging()
    fmt = logging.Formatter("%(asctime)s", datefmt=LOG_DATE_FORMAT)
    return fmt.format(_record())


def test_timestamp_shifts_with_the_tz_env_var(restore_tz):
    # A zone set after interpreter start (as .env does) must still take effect.
    assert _formatted("UTC").endswith("+0000")
    assert _formatted("Asia/Tokyo").endswith("+0900")


def test_timestamp_carries_its_utc_offset(restore_tz):
    # Without an offset a stdout line is unreadable when the container zone is unknown.
    assert _formatted("UTC").count(":") == 2


def test_buffered_records_stay_utc_for_the_api(restore_tz):
    import os

    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    handler = RingBufferHandler()
    handler.emit(_record())

    ts = handler.records()[0]["ts"]
    assert ts.endswith("+00:00")
