from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .logger import get_logger

log = get_logger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler(sync_fn):
    async def _job():
        log.info("scheduled sync: start")
        try:
            await sync_fn()
            log.info("scheduled sync: done")
        except Exception:
            log.exception("scheduled sync: failed")
            raise

    scheduler.add_job(
        _job,
        CronTrigger(hour="*/6"),
        id="sync_all_stores",
        replace_existing=True,
    )
    scheduler.start()
    log.info("scheduler started (sync every 6h)")
