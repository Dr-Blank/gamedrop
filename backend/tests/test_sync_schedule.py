"""Scheduled syncs honour each store's own `sync_interval_hours`."""

import asyncio
import json
from datetime import datetime, timedelta
from itertools import pairwise
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from app import db as _db
from app import scraper
from app.adapters.throttle import RATE_LIMITED_PREFIX
from app.models import Store, SyncLog
from app.scheduler import TICK, start_scheduler
from app.scraper import (
    MAX_REFUSED_INTERVAL,
    SCHEDULE_JITTER,
    due_stores,
    jitter,
    scheduled_interval,
    sync_due_stores,
    sync_interval,
)

T0 = datetime(2026, 1, 1, 0, 0)
SLACK = TICK / 2


@pytest.fixture(autouse=True)
def exact_schedule(monkeypatch):
    """Pin jitter so schedules land on exact hours; jitter tests restore it."""
    monkeypatch.setattr(scraper, "jitter", lambda *_: 1.0)


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

    def __init__(
        self,
        start: datetime,
        fail: frozenset[str] = frozenset(),
        refuse: frozenset[str] = frozenset(),
    ):
        self.now = start
        self.fail = fail
        self.refuse = set(refuse)
        self.calls: list[tuple[str, datetime]] = []
        self.start_delay = timedelta(0)

    def _error(self, store_id: str) -> str | None:
        if store_id in self.refuse:
            return f"{RATE_LIMITED_PREFIX}, next try in 1h"
        return "boom" if store_id in self.fail else None

    async def __call__(self, store: Store):
        started = self.now + self.start_delay
        self.calls.append((store.id, started))
        error = self._error(store.id)
        with Session(_db.engine) as session:
            session.add(
                SyncLog(
                    store_id=store.id,
                    started_at=started,
                    finished_at=started,
                    error=error,
                )
            )
            session.commit()
        if error:
            raise RuntimeError(error)

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


def test_a_refusing_shop_is_asked_half_as_often_each_time(session: Session):
    _store(session, "refusing", hours=6)
    _store(session, "fine", hours=6)

    clock = _Clock(T0, refuse={"refusing"})
    _run_ticks(clock, hours=48)

    assert _hours(clock.times("refusing")) == [0, 12, 36]
    assert _hours(clock.times("fine")) == [6 * i for i in range(9)]


def test_other_errors_do_not_slow_the_schedule(session: Session):
    _store(session, "broken", hours=6)

    clock = _Clock(T0, fail={"broken"})
    _run_ticks(clock, hours=24)

    assert _hours(clock.times("broken")) == [0, 6, 12, 18, 24]


def test_a_successful_sync_or_import_ends_the_backoff(session: Session):
    _store(session, "shop", hours=6)
    clock = _Clock(T0, refuse={"shop"})
    _run_ticks(clock, hours=12)
    assert _hours(clock.times("shop")) == [0, 12]

    session.add(SyncLog(store_id="shop", started_at=T0 + timedelta(hours=13)))
    session.commit()

    assert due_stores(T0 + timedelta(hours=18)) == []
    assert [s.id for s in due_stores(T0 + timedelta(hours=19))] == ["shop"]


def test_backoff_stops_at_a_week_and_never_shortens_a_longer_interval(
    session: Session,
):
    daily = _store(session, "daily", hours=24)
    fortnightly = _store(session, "fortnightly", hours=24 * 14)

    assert scheduled_interval(daily, 0) == timedelta(hours=24)
    assert scheduled_interval(daily, 2) == timedelta(hours=96)
    assert scheduled_interval(daily, 8) == MAX_REFUSED_INTERVAL
    assert scheduled_interval(fortnightly, 3) == timedelta(days=14)


def test_jitter_stays_near_one_and_agrees_with_itself():
    factors = [jitter("shop", T0 + timedelta(hours=h)) for h in range(50)]

    assert all(1 - SCHEDULE_JITTER <= f <= 1 + SCHEDULE_JITTER for f in factors)
    assert len(set(factors)) == len(factors)
    assert jitter("shop", T0) == jitter("shop", T0)
    assert jitter("shop", T0) != jitter("other", T0)


def test_daily_syncs_drift_around_a_day_rather_than_landing_on_it(
    session: Session, monkeypatch
):
    monkeypatch.setattr(scraper, "jitter", jitter)
    _store(session, "daily", hours=24)

    clock = _Clock(T0)
    _run_ticks(clock, hours=24 * 20)

    times = clock.times("daily")
    gaps = [(b - a) / timedelta(hours=1) for a, b in pairwise(times)]
    low, high = 24 * (1 - SCHEDULE_JITTER), 24 * (1 + SCHEDULE_JITTER)
    assert len(gaps) >= 15
    assert all(low - 0.25 <= g <= high + 0.25 for g in gaps)
    assert len(set(gaps)) > 3


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
        assert sync_interval(store) == timedelta(hours=24)


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


def test_planner_stats_refresh_only_after_stores_sync(session: Session):
    _store(session, "a", hours=6)
    clock = _Clock(T0)
    with (
        patch("app.scraper.sync_store", clock),
        patch("app.db.refresh_stats") as refresh,
    ):
        asyncio.run(sync_due_stores(T0, slack=SLACK))
        assert refresh.call_count == 1

        asyncio.run(sync_due_stores(T0 + TICK, slack=SLACK))
        assert refresh.call_count == 1


def test_a_shop_waiting_out_a_limit_does_not_hold_up_the_others(session: Session):
    _store(session, "slow", hours=6)
    _store(session, "quick", hours=6)

    async def run():
        quick_done = asyncio.Event()

        async def fake_sync(store: Store):
            if store.id == "slow":
                await quick_done.wait()
            else:
                quick_done.set()

        with patch("app.scraper.sync_store", fake_sync):
            await asyncio.wait_for(sync_due_stores(T0), timeout=5)

    asyncio.run(run())
