"""NewsSnap AI - Feed API Router (Issue 17).

Provides personalized news snap feed with cursor-based pagination,
category/language/time-range filtering, and Redis caching.
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.middleware import get_optional_current_user
from src.config.database import get_db
from src.config.settings import Language, settings
from src.models.user import User
from src.recommendation.engine import RecommendationEngine
from src.utils.cache import (
    build_feed_cache_key,
    get_cached_feed,
    invalidate_feed_cache,
    set_cached_feed,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feed", tags=["feed"])
engine = RecommendationEngine()


class FeedItem(BaseModel):
    """Schema for individual snap item in the feed."""

    snap_id: str
    article_id: str
    title: str
    summary: str
    image_url: Optional[str] = None
    category: str
    source: str
    time_ago: str
    interaction_counts: Dict[str, int]


class FeedResponse(BaseModel):
    """Response schema for personalized feed."""

    items: List[FeedItem]
    snaps: List[FeedItem] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False


def encode_cursor(cursor_data: Dict[str, Any]) -> str:
    """Encode cursor dict to a URL-safe base64 string.

    Args:
        cursor_data: Dictionary containing pagination offset.

    Returns:
        Base64 string.
    """
    json_bytes = json.dumps(cursor_data).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("utf-8")


def decode_cursor(cursor_str: str) -> Dict[str, Any]:
    """Decode a URL-safe base64 cursor string into a dict.

    Args:
        cursor_str: Base64 string.

    Returns:
        Decoded dictionary.

    Raises:
        HTTPException: If cursor is malformed or invalid.
    """
    try:
        raw_bytes = base64.urlsafe_b64decode(cursor_str.encode("utf-8"))
        data = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Cursor must be a JSON object")
        return data
    except Exception as e:
        logger.warning(f"Failed to decode cursor: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor format",
        )


@router.get("", response_model=FeedResponse)
@router.get("/", response_model=FeedResponse, include_in_schema=False)
def get_feed(
    language: Optional[str] = Query(None, description="Language code (required, e.g. en, hi, ta, te, kn)"),
    categories: Optional[str] = Query(None, description="Comma-separated category slugs"),
    time_range: Optional[str] = Query(None, description="Time range window (e.g. 24h, 7d, 30d)"),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    limit: int = Query(20, ge=1, le=100, description="Number of snaps to return (1-100)"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Retrieve personalized news snaps with cursor-based pagination.

    - Language filter is required (returns 400 if omitted or unsupported).
    - Category filter narrows results to selected categories.
    - Cursor pagination enables infinite scrolling.
    - Results are cached in Redis for fast (< 200ms) responses.
    """
    # 1. Validate required language filter
    if not language or not language.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Language filter is required",
        )

    clean_lang = language.strip().lower()
    valid_langs = {lang.value for lang in Language}
    valid_langs.update(settings.SUPPORTED_LANGUAGES)

    if clean_lang not in valid_langs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{language}'. Supported: {sorted(list(valid_langs))}",
        )

    # 2. Parse category filter
    category_list: Optional[List[str]] = None
    if categories:
        category_list = [c.strip().lower() for c in categories.split(",") if c.strip()]
        if not category_list:
            category_list = None

    # 3. Parse pagination cursor
    offset = 0
    if cursor:
        cursor_data = decode_cursor(cursor)
        offset = cursor_data.get("offset", 0)
        if not isinstance(offset, int) or offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid offset in pagination cursor",
            )

    # 4. Check Redis cache for pre-computed top 50 feed items
    user_id_str = str(current_user.id) if current_user else None
    cache_key = build_feed_cache_key(
        user_id=user_id_str,
        language=clean_lang,
        categories=category_list,
        time_range=time_range,
    )

    cached_items = get_cached_feed(cache_key)

    if cached_items is not None:
        feed_items = cached_items
    else:
        # Cache miss: compute top 50 feed items via RecommendationEngine
        feed_items = engine.get_feed(
            user=current_user,
            language=clean_lang,
            categories=category_list,
            time_range=time_range,
            limit=50,
            db=db,
        )
        # Store in Redis
        set_cached_feed(cache_key, feed_items, ttl=300)

    # 5. Slice page according to offset and limit
    total_available = len(feed_items)
    if offset >= total_available:
        paged_items = []
        has_more = False
        next_cursor = None
    else:
        paged_items = feed_items[offset : offset + limit]
        has_more = (offset + limit) < total_available
        next_cursor = encode_cursor({"offset": offset + limit}) if has_more else None

    # 6. Format response
    formatted_items = [FeedItem(**item) for item in paged_items]

    return FeedResponse(
        items=formatted_items,
        snaps=formatted_items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/cache/invalidate")
def invalidate_cache(
    user_id: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """Invalidate pre-computed feed caches in Redis."""
    target_id = user_id or (str(current_user.id) if current_user else None)
    deleted = invalidate_feed_cache(target_id)
    return {"status": "ok", "deleted_keys": deleted}
