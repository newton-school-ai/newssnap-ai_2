"""NewsSnap AI - Trending, Breaking News, and Explore API Router (Issue 20).

Endpoints:
- GET /api/trending: Articles ranked by interaction velocity in the last 1 hour
- GET /api/breaking: High-velocity recent articles (< 30 minutes old)
- GET /api/explore: Combined Explore feed (breaking + trending + top per category)
- POST /api/trending/refresh: Force recomputation and cache refresh
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.api.middleware import get_optional_current_user
from src.config.database import get_db
from src.config.settings import settings
from src.models.user import User
from src.recommendation.trending import (
    detect_breaking_news,
    get_explore_feed,
    get_trending_articles,
    refresh_all_trending_caches,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trending"])


@router.get("/api/trending")
def get_trending(
    language: Optional[str] = Query(default="en", description="Filter by language code (e.g. en, hi)"),
    limit: int = Query(default=10, ge=1, le=100, description="Max number of articles to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    category: Optional[str] = Query(default=None, description="Optional category slug filter"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get articles ranked by interaction velocity over the last 1 hour.
    Backed by Redis-cached velocity scores. Response time < 100ms.
    """
    articles = get_trending_articles(
        db,
        language=language,
        category_slug=category,
        limit=limit,
        offset=offset,
        window_hours=settings.TRENDING_WINDOW_HOURS,
    )

    return {
        "trending": articles,
        "articles": articles,
        "items": articles,
        "count": len(articles),
        "limit": limit,
        "offset": offset,
        "language": language or "en",
    }


@router.get("/api/breaking")
def get_breaking(
    language: Optional[str] = Query(default="en", description="Filter by language code"),
    threshold: Optional[float] = Query(default=None, description="Minimum velocity threshold"),
    limit: int = Query(default=5, ge=1, le=50, description="Max number of breaking articles"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Detect breaking news: articles < 30 minutes old with interaction velocity > threshold.
    """
    thresh = threshold if threshold is not None else settings.BREAKING_NEWS_VELOCITY_THRESHOLD
    articles = detect_breaking_news(
        db,
        language=language,
        threshold=thresh,
        max_age_minutes=settings.BREAKING_NEWS_MAX_AGE_MINUTES,
        limit=limit,
    )

    return {
        "breaking": articles,
        "articles": articles,
        "items": articles,
        "count": len(articles),
        "threshold": thresh,
        "language": language or "en",
    }


@router.get("/api/explore")
def get_explore(
    language: Optional[str] = Query(default="en", description="Filter by language code"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get the explore page feed combining:
    - Breaking news (if any)
    - Trending articles
    - Top articles per category (last 24 hours)
    Supports optional Bearer token authentication.
    """
    feed = get_explore_feed(
        db,
        language=language,
        trending_limit=10,
        category_top_limit=4,
    )
    if current_user:
        feed["user_id"] = str(current_user.id)
    return feed


@router.post("/api/trending/refresh", status_code=status.HTTP_200_OK)
def refresh_trending(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Trigger manual recomputation of velocity scores and warm all Redis caches.
    """
    summary = refresh_all_trending_caches(db)
    return {
        "status": "refreshed",
        "summary": summary,
    }
