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
TRENDING_JOB_ID = "periodic_trending_refresh_job"
COLLABORATIVE_RETRAIN_JOB_ID = "periodic_collaborative_retrain_job"
RECOMMENDATION_REFRESH_JOB_ID = "periodic_recommendation_refresh_job"
DEFAULT_INTERVAL_MINUTES = 10
DEFAULT_TRENDING_INTERVAL_MINUTES = 5
DEFAULT_RETRAIN_INTERVAL_HOURS = 6
DEFAULT_RECOMMENDATION_REFRESH_INTERVAL_MINUTES = 30


def _run_recommendation_refresh_sync():
    """Sync wrapper to refresh and precompute recommendation feeds for active users."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.refresh import refresh_user_feeds

        db = SessionLocal()
        try:
            result = refresh_user_feeds(db)
            logger.info(
                f"Scheduled recommendation refresh completed: {result.get('total_users', 0)} users, "
                f"{result.get('feeds_cached', 0)} feeds cached in {result.get('duration_seconds', 0.0):.2f}s"
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled recommendation refresh: {e}", exc_info=True)


async def _run_recommendation_refresh_async():
    """Async wrapper to refresh and precompute recommendation feeds for active users."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.refresh import refresh_user_feeds

        db = SessionLocal()
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, refresh_user_feeds, db)
            logger.info(
                f"Scheduled async recommendation refresh completed: {result.get('total_users', 0)} users, "
                f"{result.get('feeds_cached', 0)} feeds cached in {result.get('duration_seconds', 0.0):.2f}s"
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled recommendation refresh: {e}", exc_info=True)


def _run_collaborative_retrain_sync():
    """Sync wrapper to retrain collaborative filtering ALS model."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.collaborative import get_collaborative_recommender

        db = SessionLocal()
        try:
            recommender = get_collaborative_recommender()
            recommender.fit_from_db(db)
            logger.info("Scheduled collaborative model retrain completed successfully.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled collaborative retrain: {e}", exc_info=True)


async def _run_collaborative_retrain_async():
    """Async wrapper to retrain collaborative filtering ALS model."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.collaborative import get_collaborative_recommender

        db = SessionLocal()
        try:
            recommender = get_collaborative_recommender()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, recommender.fit_from_db, db)
            logger.info("Scheduled async collaborative model retrain completed successfully.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled collaborative retrain: {e}", exc_info=True)


def _run_trending_sync():
    """Sync wrapper to refresh trending caches."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.trending import refresh_all_trending_caches

        db = SessionLocal()
        try:
            refresh_all_trending_caches(db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled trending cache refresh: {e}", exc_info=True)


async def _run_trending_async():
    """Async wrapper to refresh trending caches."""
    try:
        from src.config.database import SessionLocal
        from src.recommendation.trending import refresh_all_trending_caches

        db = SessionLocal()
        try:
            refresh_all_trending_caches(db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error executing scheduled trending cache refresh: {e}", exc_info=True)


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
    trending_interval_minutes: int = DEFAULT_TRENDING_INTERVAL_MINUTES,
    retrain_interval_hours: int = DEFAULT_RETRAIN_INTERVAL_HOURS,
    recommendation_interval_minutes: int = DEFAULT_RECOMMENDATION_REFRESH_INTERVAL_MINUTES,
) -> AsyncIOScheduler | BackgroundScheduler:
    """Create and configure an APScheduler instance for scraping, trending, CF retrain, and recommendation refresh."""
    global _async_scheduler, _bg_scheduler

    trigger = IntervalTrigger(minutes=interval_minutes)
    trending_trigger = IntervalTrigger(minutes=trending_interval_minutes)
    retrain_trigger = IntervalTrigger(hours=retrain_interval_hours)
    recommendation_trigger = IntervalTrigger(minutes=recommendation_interval_minutes)

    if async_mode:
        if _async_scheduler is None:
            _async_scheduler = AsyncIOScheduler()
        # Remove existing job if any
        if _async_scheduler.get_job(SCRAPE_JOB_ID):
            _async_scheduler.remove_job(SCRAPE_JOB_ID)
        if _async_scheduler.get_job(TRENDING_JOB_ID):
            _async_scheduler.remove_job(TRENDING_JOB_ID)
        if _async_scheduler.get_job(COLLABORATIVE_RETRAIN_JOB_ID):
            _async_scheduler.remove_job(COLLABORATIVE_RETRAIN_JOB_ID)
        if _async_scheduler.get_job(RECOMMENDATION_REFRESH_JOB_ID):
            _async_scheduler.remove_job(RECOMMENDATION_REFRESH_JOB_ID)

        _async_scheduler.add_job(
            _run_scrape_async,
            trigger=trigger,
            id=SCRAPE_JOB_ID,
            name="News Scrape Pipeline (Every 10 mins)",
            replace_existing=True,
        )
        _async_scheduler.add_job(
            _run_trending_async,
            trigger=trending_trigger,
            id=TRENDING_JOB_ID,
            name="Trending & Explore Cache Refresh (Every 5 mins)",
            replace_existing=True,
        )
        _async_scheduler.add_job(
            _run_collaborative_retrain_async,
            trigger=retrain_trigger,
            id=COLLABORATIVE_RETRAIN_JOB_ID,
            name="Collaborative Filtering ALS Retrain (Every 6 hours)",
            replace_existing=True,
        )
        _async_scheduler.add_job(
            _run_recommendation_refresh_async,
            trigger=recommendation_trigger,
            id=RECOMMENDATION_REFRESH_JOB_ID,
            name="Recommendation Feed Precompute Refresh (Every 30 mins)",
            replace_existing=True,
        )
        return _async_scheduler
    else:
        if _bg_scheduler is None:
            _bg_scheduler = BackgroundScheduler()
        if _bg_scheduler.get_job(SCRAPE_JOB_ID):
            _bg_scheduler.remove_job(SCRAPE_JOB_ID)
        if _bg_scheduler.get_job(TRENDING_JOB_ID):
            _bg_scheduler.remove_job(TRENDING_JOB_ID)
        if _bg_scheduler.get_job(COLLABORATIVE_RETRAIN_JOB_ID):
            _bg_scheduler.remove_job(COLLABORATIVE_RETRAIN_JOB_ID)
        if _bg_scheduler.get_job(RECOMMENDATION_REFRESH_JOB_ID):
            _bg_scheduler.remove_job(RECOMMENDATION_REFRESH_JOB_ID)

        _bg_scheduler.add_job(
            _run_scrape_sync,
            trigger=trigger,
            id=SCRAPE_JOB_ID,
            name="News Scrape Pipeline (Every 10 mins)",
            replace_existing=True,
        )
        _bg_scheduler.add_job(
            _run_trending_sync,
            trigger=trending_trigger,
            id=TRENDING_JOB_ID,
            name="Trending & Explore Cache Refresh (Every 5 mins)",
            replace_existing=True,
        )
        _bg_scheduler.add_job(
            _run_collaborative_retrain_sync,
            trigger=retrain_trigger,
            id=COLLABORATIVE_RETRAIN_JOB_ID,
            name="Collaborative Filtering ALS Retrain (Every 6 hours)",
            replace_existing=True,
        )
        _bg_scheduler.add_job(
            _run_recommendation_refresh_sync,
            trigger=recommendation_trigger,
            id=RECOMMENDATION_REFRESH_JOB_ID,
            name="Recommendation Feed Precompute Refresh (Every 30 mins)",
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


async def trigger_recommendation_refresh_now() -> Dict[str, Any]:
    """Manually trigger a recommendation feed refresh cycle immediately."""
    logger.info("Manual recommendation refresh triggered.")
    from src.config.database import SessionLocal
    from src.recommendation.refresh import refresh_user_feeds

    db = SessionLocal()
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, refresh_user_feeds, db)
    finally:
        db.close()
