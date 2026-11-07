"""NewsSnap AI - Search API Router (Issue 18).

Provides:
- GET /api/search: Typo-tolerant multi-language search with faceted filtering and pagination
- Graceful database fallback when Meilisearch is not reachable
- Empty query trending/recent articles discovery
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.config.database import get_db
from src.models.article import Article
from src.models.snap import Snap
from src.search.meilisearch_client import meilisearch_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])


def _db_search_fallback(
    db: Session,
    query: str,
    language: str,
    category: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fallback search using SQL database when Meilisearch is unavailable."""
    start_time = time.perf_counter()

    base_query = (
        db.query(Article)
        .filter(Article.is_duplicate.is_(False))
        .options(
            joinedload(Article.source),
            joinedload(Article.category),
            joinedload(Article.snaps).joinedload(Snap.translations),
        )
    )

    if category:
        base_query = base_query.filter(Article.category.has(slug=category.lower().strip()))

    if source:
        base_query = base_query.filter(Article.source.has(slug=source.lower().strip()))

    clean_q = query.strip()
    if clean_q:
        pattern = f"%{clean_q}%"
        base_query = base_query.filter(
            or_(
                Article.title.ilike(pattern),
                Article.body.ilike(pattern),
            )
        )

    base_query = base_query.order_by(Article.publish_time.desc())

    total = base_query.count()
    articles = base_query.offset(offset).limit(limit).all()

    results: List[Dict[str, Any]] = []
    cat_distribution: Dict[str, int] = {}
    src_distribution: Dict[str, int] = {}

    for art in articles:
        snap = art.snaps[0] if (hasattr(art, "snaps") and art.snaps) else None
        cat_slug = art.category.slug if art.category else "national"
        src_slug = art.source.slug if art.source else "unknown"
        src_name = art.source.name if art.source else "Unknown"

        cat_distribution[cat_slug] = cat_distribution.get(cat_slug, 0) + 1
        src_distribution[src_slug] = src_distribution.get(src_slug, 0) + 1

        summary = snap.summary if snap else (art.body[:200] if art.body else "")
        # Check translation if requested
        if snap and language != "en" and hasattr(snap, "translations"):
            for tr in snap.translations:
                tr_lang = getattr(tr.language, "value", str(tr.language))
                if tr_lang == language and tr.summary:
                    summary = tr.summary
                    break

        results.append(
            {
                "id": str(art.id),
                "article_id": str(art.id),
                "snap_id": str(snap.id) if snap else None,
                "title": art.title,
                "summary": summary,
                "category": cat_slug,
                "source": src_slug,
                "source_name": src_name,
                "image_url": art.image_url or (snap.image_url if snap else ""),
                "source_url": art.source_url,
                "publish_time": art.publish_time.isoformat() if art.publish_time else None,
                "language": language,
            }
        )

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "results": results,
        "total": total,
        "processing_time_ms": elapsed_ms,
        "facets": {
            "category": cat_distribution,
            "source": src_distribution,
        },
    }


@router.get("")
def search_articles(
    q: Optional[str] = Query(default="", description="Search query string"),
    language: str = Query(default="en", description="Language preference (en, hi, ta, te, kn)"),
    category: Optional[str] = Query(default=None, description="Filter by category slug"),
    source: Optional[str] = Query(default=None, description="Filter by source slug"),
    start_date: Optional[str] = Query(default=None, description="Start publish date filter"),
    end_date: Optional[str] = Query(default=None, description="End publish date filter"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    page: Optional[int] = Query(default=None, ge=1, description="Page number (1-indexed)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Search articles and snaps with typo tolerance, multilingual matching, and faceted filters.
    Empty queries return recent/trending articles.
    """
    query_str = (q or "").strip()
    target_language = language.lower().strip() or "en"

    # Support page query param as alternative to offset
    resolved_offset = offset
    if page is not None:
        resolved_offset = (page - 1) * limit

    resolved_page = (resolved_offset // limit) + 1

    try:
        # Check Meilisearch health and search
        if meilisearch_client.is_healthy():
            search_response = meilisearch_client.search(
                query=query_str,
                category=category,
                source=source,
                start_date=start_date,
                end_date=end_date,
                target_language=target_language,
                limit=limit,
                offset=resolved_offset,
                facets=["category", "source"],
            )

            hits = search_response.get("hits", [])
            total = search_response.get("total", len(hits))
            facet_dist = search_response.get("facet_distribution", {})
            proc_time = search_response.get("processing_time_ms", 1.0)

            # Standardize returned hits to match API snap metadata format
            formatted_results: List[Dict[str, Any]] = []
            for h in hits:
                formatted_results.append(
                    {
                        "id": str(h.get("id")),
                        "article_id": str(h.get("article_id") or h.get("id")),
                        "snap_id": h.get("snap_id"),
                        "title": h.get("title", ""),
                        "summary": h.get("summary", ""),
                        "category": h.get("category", "national"),
                        "source": h.get("source", "unknown"),
                        "source_name": h.get("source_name", "Unknown"),
                        "image_url": h.get("image_url", ""),
                        "source_url": h.get("source_url", ""),
                        "publish_time": h.get("publish_time_iso")
                        or (
                            datetime.fromtimestamp(h["publish_time"]).isoformat()
                            if isinstance(h.get("publish_time"), (int, float))
                            else None
                        ),
                        "language": target_language,
                    }
                )

            # If Meilisearch has no documents yet (empty index), fallback to DB
            if total == 0 and not query_str:
                fallback = _db_search_fallback(
                    db=db,
                    query=query_str,
                    language=target_language,
                    category=category,
                    source=source,
                    limit=limit,
                    offset=resolved_offset,
                )
                if fallback["total"] > 0:
                    formatted_results = fallback["results"]
                    total = fallback["total"]
                    facet_dist = fallback["facets"]
                    proc_time = fallback["processing_time_ms"]

            return {
                "query": query_str,
                "language": target_language,
                "total": total,
                "limit": limit,
                "offset": resolved_offset,
                "page": resolved_page,
                "total_pages": math.ceil(total / limit) if limit > 0 else 1,
                "processing_time_ms": proc_time,
                "results": formatted_results,
                "facets": {
                    "category": facet_dist.get("category", {}),
                    "source": facet_dist.get("source", {}),
                },
            }

    except Exception as e:
        logger.warning(f"Meilisearch query failed, falling back to database: {e}")

    # Fallback to database search
    fallback_data = _db_search_fallback(
        db=db,
        query=query_str,
        language=target_language,
        category=category,
        source=source,
        limit=limit,
        offset=resolved_offset,
    )

    total = fallback_data["total"]
    return {
        "query": query_str,
        "language": target_language,
        "total": total,
        "limit": limit,
        "offset": resolved_offset,
        "page": resolved_page,
        "total_pages": math.ceil(total / limit) if limit > 0 else 1,
        "processing_time_ms": fallback_data["processing_time_ms"],
        "results": fallback_data["results"],
        "facets": fallback_data["facets"],
    }
