"""Scheduled syncs honour each store's own `sync_interval_hours`."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlmodel import Session

from app import db as _db
from app.models import Store, SyncLog
from app.scheduler import TICK, start_scheduler
from app.scraper import due_stores, sync_due_stores, sync_interval

T0 = datetime(2026, 1, 1, 0, 0)
SLACK = TICK / 2


def _store(session: Session, store_id: str, hours=None, **fields) -> Store:
    config = {"timeout_sec": 30, "request_delay_sec": 1}
    if hours is not None:
        config["sync_interval_hours"] = hours
    store = Store(
        id=store_id,
        name=store_id,
        type="shopify",
        base_url=f"https://{store_id}.com",
        scrape_config=json.dumps(config),
        **fields,
    )
    session.add(store)
    session.commit()
    return store


class _Clock:
    """Fake `sync_store` that logs each attempt at the simulated time."""

    def __init__(self, start: datetime, fail: set[str] = frozenset()):
        self.now = start
        self.fail = fail
        self.calls: list[tuple[str, datetime]] = []
        self.start_delay = timedelta(0)

    async def __call__(self, store: Store):
        started = self.now + self.start_delay
        self.calls.append((store.id, started))
        with Session(_db.engine) as session:
            session.add(
                SyncLog(
                    store_id=store.id,
                    started_at=started,
                    finished_at=started,
                    error="boom" if store.id in self.fail else None,
                )
            )
            session.commit()
        if store.id in self.fail:
            raise RuntimeError("boom")

    def times(self, store_id: str) -> list[datetime]:
        return [t for s, t in self.calls if s == store_id]


def _run_ticks(clock: _Clock, hours: int):
    with patch("app.scraper.sync_store", clock):
        for i in range(int(timedelta(hours=hours) / TICK) + 1):
            clock.now = T0 + i * TICK
            asyncio.run(sync_due_stores(clock.now, slack=SLACK))


def _hours(times: list[datetime]) -> list[float]:
    return [(t - T0).total_seconds() / 3600 for t in times]


def test_stores_with_different_intervals_sync_on_their_own_schedules(
    session: Session,
):
    _store(session, "six", hours=6)
    _store(session, "eight", hours=8)
    _store(session, "daily", hours=24)

    clock = _Clock(T0)
    _run_ticks(clock, hours=24)

    assert _hours(clock.times("six")) == [0, 6, 12, 18, 24]
    assert _hours(clock.times("eight")) == [0, 8, 16, 24]
    assert _hours(clock.times("daily")) == [0, 24]


def test_a_late_start_does_not_drift_the_schedule(session: Session):
    _store(session, "eight", hours=8)

    clock = _Clock(T0)
    clock.start_delay = timedelta(minutes=5)
    _run_ticks(clock, hours=24)

    assert [round(h, 2) for h in _hours(clock.times("eight"))] == [
        0.08,
        8.08,
        16.08,
        24.08,
    ]


def test_changing_the_interval_takes_effect_without_a_restart(session: Session):
    store = _store(session, "shop", hours=6)
    session.add(SyncLog(store_id="shop", started_at=T0))
    session.commit()

    assert [s.id for s in due_stores(T0 + timedelta(hours=6))] == ["shop"]

    store.scrape_config = json.dumps({"sync_interval_hours": 8})
    session.add(store)
    session.commit()

    assert due_stores(T0 + timedelta(hours=6)) == []
    assert [s.id for s in due_stores(T0 + timedelta(hours=8))] == ["shop"]


def test_a_failing_store_waits_its_interval_and_spares_the_others(session: Session):
    _store(session, "broken", hours=6)
    _store(session, "fine", hours=6)

    clock = _Clock(T0, fail={"broken"})
    _run_ticks(clock, hours=12)

    assert _hours(clock.times("broken")) == [0, 6, 12]
    assert _hours(clock.times("fine")) == [0, 6, 12]


def test_a_manual_sync_restarts_the_stores_clock(session: Session):
    _store(session, "shop", hours=8)
    session.add(SyncLog(store_id="shop", started_at=T0))
    session.add(SyncLog(store_id="shop", started_at=T0 + timedelta(hours=5)))
    session.commit()

    assert due_stores(T0 + timedelta(hours=8)) == []
    assert [s.id for s in due_stores(T0 + timedelta(hours=13))] == ["shop"]


def test_disabled_stores_are_never_due(session: Session):
    _store(session, "off", hours=1, enabled=False)
    assert due_stores(T0) == []


def test_never_synced_store_is_due_immediately(session: Session):
    _store(session, "new", hours=24)
    assert [s.id for s in due_stores(T0)] == ["new"]


def test_missing_or_bad_interval_falls_back_to_default(session: Session):
    missing = _store(session, "missing")
    junk = _store(session, "junk", hours="soon")
    zero = _store(session, "zero", hours=0)
    broken = _store(session, "broken-json")
    broken.scrape_config = "{not json"

    for store in (missing, junk, zero, broken):
        assert sync_interval(store) == timedelta(hours=6)


def test_fractional_interval_is_honoured(session: Session):
    store = _store(session, "fast", hours=1.5)
    assert sync_interval(store) == timedelta(minutes=90)


def test_scheduler_ticks_often_and_passes_slack():
    fake = MagicMock()
    sync_fn = MagicMock()

    async def _sync(**kwargs):
        sync_fn(**kwargs)

    with patch("app.scheduler.scheduler", fake):
        start_scheduler(_sync)

    job, trigger = fake.add_job.call_args.args
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "*/15"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "*"

    asyncio.run(job())
    sync_fn.assert_called_once_with(slack=SLACK)
