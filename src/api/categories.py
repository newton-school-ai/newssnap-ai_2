"""NewsSnap AI - Category API Router (Issue 20).

Endpoints:
- GET /api/categories: List categories with article counts
- GET /api/categories/{category_slug}/top: Top articles in category from last 24 hours
- GET /api/categories/{category_slug}: Category metadata with article count
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.config.settings import settings
from src.models.article import Article
from src.models.category import Category
from src.recommendation.trending import get_top_articles_by_category
from src.utils.cache import get_cache, set_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["categories"])


@router.get("/api/categories")
def list_categories(
    language: Optional[str] = Query(default=None, description="Optional language filter for article count"),
    active_only: bool = Query(default=True, description="Filter for active categories only"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all categories with their article counts.
    Cached in Redis with 5-minute TTL.
    """
    norm_lang = language.lower().strip() if (language and language.lower() not in ("all", "*")) else None
    cache_key = f"categories:list:{norm_lang or 'all'}:{active_only}"

    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    cat_query = db.query(Category)
    if active_only:
        cat_query = cat_query.filter(Category.is_active.is_(True))

    categories = cat_query.order_by(Category.name.asc()).all()

    # Calculate article counts per category
    art_count_query = db.query(
        Article.category_id,
        func.count(Article.id).label("count"),
    ).filter(Article.is_duplicate.is_(False))

    if norm_lang:
        art_count_query = art_count_query.filter(Article.language == norm_lang)

    counts_by_cat = dict(art_count_query.group_by(Article.category_id).all())

    cat_list = [
        {
            "id": cat.id,
            "slug": cat.slug,
            "name": cat.name,
            "article_count": counts_by_cat.get(cat.id, 0),
            "is_active": cat.is_active,
        }
        for cat in categories
    ]

    result = {
        "categories": cat_list,
        "items": cat_list,
        "total": len(cat_list),
        "language": norm_lang or "all",
    }

    set_cache(cache_key, result, ttl_seconds=settings.TRENDING_CACHE_TTL_SECONDS)
    return result


@router.get("/api/categories/{category_slug}/top")
def get_category_top_articles(
    category_slug: str,
    language: Optional[str] = Query(default="en", description="Filter by language code"),
    limit: int = Query(default=10, ge=1, le=100, description="Max articles to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve top articles in a category from the last 24 hours.
    Returns 404 if category slug is not found.
    """
    slug = category_slug.lower().strip()
    cat = db.query(Category).filter(Category.slug == slug).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_slug}' not found",
        )

    articles = get_top_articles_by_category(
        db,
        category_slug=slug,
        language=language,
        limit=limit,
        offset=offset,
        window_hours=24,
    )

    if articles is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_slug}' not found",
        )

    return {
        "category": {
            "id": cat.id,
            "slug": cat.slug,
            "name": cat.name,
            "is_active": cat.is_active,
        },
        "articles": articles,
        "items": articles,
        "count": len(articles),
        "limit": limit,
        "offset": offset,
        "language": language or "en",
    }


@router.get("/api/categories/{category_slug}")
def get_category_details(
    category_slug: str,
    language: Optional[str] = Query(default=None, description="Optional language filter for article count"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get category details and its total article count.
    """
    slug = category_slug.lower().strip()
    cat = db.query(Category).filter(Category.slug == slug).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_slug}' not found",
        )

    art_query = db.query(func.count(Article.id)).filter(
        Article.category_id == cat.id,
        Article.is_duplicate.is_(False),
    )
    norm_lang = language.lower().strip() if (language and language.lower() not in ("all", "*")) else None
    if norm_lang:
        art_query = art_query.filter(Article.language == norm_lang)

    count = art_query.scalar() or 0

    return {
        "id": cat.id,
        "slug": cat.slug,
        "name": cat.name,
        "article_count": count,
        "is_active": cat.is_active,
    }
