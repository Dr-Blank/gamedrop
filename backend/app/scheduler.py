from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()


def start_scheduler(sync_fn):
    scheduler.add_job(
        sync_fn,
        CronTrigger(hour="*/6"),
        id="sync_all_stores",
        replace_existing=True,
    )
    scheduler.start()
