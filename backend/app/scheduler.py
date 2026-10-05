from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .logger import get_logger

log = get_logger(__name__)

scheduler = AsyncIOScheduler()

#: How often due stores are checked; each store's own interval decides if it runs.
TICK = timedelta(minutes=15)


def start_scheduler(sync_fn):
    async def _job():
        log.info("scheduled sync: start")
        try:
            # Half a tick of slack rounds each store to its nearest tick, so a
            # sync that started late doesn't slip a whole tick every cycle.
            await sync_fn(slack=TICK / 2)
            log.info("scheduled sync: done")
        except Exception:
            log.exception("scheduled sync: failed")
            raise

    scheduler.add_job(
        _job,
        CronTrigger(minute=f"*/{int(TICK.total_seconds() // 60)}"),
        id="sync_all_stores",
        replace_existing=True,
    )
    scheduler.start()
    log.info("scheduler started (checking due stores every %s)", TICK)
