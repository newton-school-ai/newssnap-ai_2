"""NewsSnap AI - Admin and Health Monitoring API (Issue 8).

Endpoints:
- GET /api/admin/scrape-health: per-source health metrics and pipeline throughput
- GET /api/admin/recent-articles: recent articles fetched by the scraper
- POST /api/admin/trigger-scrape: manually trigger a scrape cycle
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.scheduler.scrape_pipeline import pipeline_instance

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/scrape-health")
def get_scrape_health(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get comprehensive health metrics for the news scraping pipeline.
    Returns per-source health status, success/error counts, cooldown status, and throughput.
    """
    return pipeline_instance.get_health_metrics(db=db)


@router.get("/recent-articles")
def get_recent_articles(
    limit: int = Query(default=10, ge=1, le=100, description="Max number of articles to return"),
    source_slug: Optional[str] = Query(default=None, description="Filter by source slug"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Get the most recently scraped articles stored in the database.
    """
    return pipeline_instance.get_recent_articles(db=db, limit=limit, source_slug=source_slug)


@router.post("/trigger-scrape")
async def trigger_scrape(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Manually trigger an immediate scraping cycle across all sources.
    """
    result = await pipeline_instance.run_scrape_cycle(db=db)
    return {"status": "completed", "result": result}
