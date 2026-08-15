"""NewsSnap AI - APScheduler Jobs and Scheduler Management (Issue 8).

Configures and manages periodic news scraping tasks:
- Triggers scrape pipeline every 10 minutes
- Spreads source execution across the interval
- Handles errors gracefully
- Provides start, stop, status, and manual trigger controls
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler.scrape_pipeline import pipeline_instance

logger = logging.getLogger(__name__)

# Global scheduler references
_async_scheduler: Optional[AsyncIOScheduler] = None
_bg_scheduler: Optional[BackgroundScheduler] = None
SCRAPE_JOB_ID = "periodic_news_scrape_job"
DEFAULT_INTERVAL_MINUTES = 10


def _run_scrape_sync():
    """Wrapper to run async scrape pipeline inside sync/background scheduler."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        asyncio.create_task(pipeline_instance.run_scrape_cycle())
    else:
        loop.run_until_complete(pipeline_instance.run_scrape_cycle())


async def _run_scrape_async():
    """Async wrapper to run scrape pipeline in async scheduler."""
    try:
        await pipeline_instance.run_scrape_cycle()
    except Exception as e:
        logger.error(f"Error executing scheduled scrape cycle: {e}", exc_info=True)


def create_scheduler(
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    async_mode: bool = True,
) -> AsyncIOScheduler | BackgroundScheduler:
    """Create and configure an APScheduler instance for the 10-minute scraping cycle."""
    global _async_scheduler, _bg_scheduler

    trigger = IntervalTrigger(minutes=interval_minutes)

    if async_mode:
        if _async_scheduler is None:
            _async_scheduler = AsyncIOScheduler()
        # Remove existing job if any
        if _async_scheduler.get_job(SCRAPE_JOB_ID):
            _async_scheduler.remove_job(SCRAPE_JOB_ID)
        _async_scheduler.add_job(
            _run_scrape_async,
            trigger=trigger,
            id=SCRAPE_JOB_ID,
            name="News Scrape Pipeline (Every 10 mins)",
            replace_existing=True,
        )
        return _async_scheduler
    else:
        if _bg_scheduler is None:
            _bg_scheduler = BackgroundScheduler()
        if _bg_scheduler.get_job(SCRAPE_JOB_ID):
            _bg_scheduler.remove_job(SCRAPE_JOB_ID)
        _bg_scheduler.add_job(
            _run_scrape_sync,
            trigger=trigger,
            id=SCRAPE_JOB_ID,
            name="News Scrape Pipeline (Every 10 mins)",
            replace_existing=True,
        )
        return _bg_scheduler


def start_scheduler(
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    async_mode: bool = False,
) -> BackgroundScheduler | AsyncIOScheduler:
    """
    Start the scrape scheduler.
    By default runs BackgroundScheduler for simple CLI / script execution,
    or AsyncIOScheduler when integrated with FastAPI event loop.
    """
    scheduler = create_scheduler(interval_minutes=interval_minutes, async_mode=async_mode)
    if not scheduler.running:
        scheduler.start()
        logger.info(f"Scrape scheduler started. Triggering pipeline every {interval_minutes} minutes.")
    return scheduler


def stop_scheduler() -> None:
    """Stop any active schedulers."""
    global _async_scheduler, _bg_scheduler

    if _async_scheduler and _async_scheduler.running:
        _async_scheduler.shutdown(wait=False)
        logger.info("Async scrape scheduler stopped.")
        _async_scheduler = None

    if _bg_scheduler and _bg_scheduler.running:
        _bg_scheduler.shutdown(wait=False)
        logger.info("Background scrape scheduler stopped.")
        _bg_scheduler = None


def get_scheduler() -> Optional[AsyncIOScheduler | BackgroundScheduler]:
    """Get currently active scheduler."""
    if _async_scheduler and _async_scheduler.running:
        return _async_scheduler
    if _bg_scheduler and _bg_scheduler.running:
        return _bg_scheduler
    return _async_scheduler or _bg_scheduler


def is_scheduler_running() -> bool:
    """Check if any scheduler is currently running."""
    sched = get_scheduler()
    return sched is not None and sched.running


async def trigger_scrape_now() -> Dict[str, Any]:
    """Manually trigger a scrape cycle immediately."""
    logger.info("Manual scrape cycle triggered.")
    return await pipeline_instance.run_scrape_cycle()
