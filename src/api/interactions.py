"""NewsSnap AI - Interactions API Router (Issue 19).

Endpoints:
- POST /api/articles/{article_id}/like: Toggle like/unlike
- POST /api/articles/{article_id}/bookmark: Toggle bookmark/unbookmark
- POST /api/articles/{article_id}/share: Record share event
- POST /api/articles/{article_id}/read: Track snap read and time spent
- GET /api/articles/{article_id}/interactions: Get interaction counts and status
- GET /api/users/me/bookmarks: List bookmarked articles for current user
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.middleware import get_current_user, get_optional_current_user
from src.config.database import get_db
from src.models.article import Article
from src.models.interaction import Comment, Interaction, InteractionType
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interactions"])


# ------------------------------------------------------------------------------
# Request Schemas
# ------------------------------------------------------------------------------


class ReadTrackingRequest(BaseModel):
    time_spent_seconds: int = Field(default=0, ge=0, description="Time spent viewing snap in seconds")


class ShareTrackingRequest(BaseModel):
    platform: Optional[str] = Field(default="general", description="Target share platform, e.g. whatsapp, twitter")


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------


def _get_article_or_404(db: Session, article_id: str) -> Article:
    """Validate article UUID and verify existence."""
    try:
        article_uuid = uuid.UUID(str(article_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid article ID format")

    article = db.query(Article).filter(Article.id == article_uuid).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    return article


def _get_article_counts(db: Session, article_uuid: uuid.UUID) -> Dict[str, int]:
    """Calculate atomic interaction counts for an article."""
    counts = dict(
        db.query(Interaction.type, func.count(Interaction.id))
        .filter(Interaction.article_id == article_uuid)
        .group_by(Interaction.type)
        .all()
    )

    comment_count = db.query(func.count(Comment.id)).filter(Comment.article_id == article_uuid).scalar() or 0

    return {
        "like_count": counts.get(InteractionType.LIKE.value, 0),
        "bookmark_count": counts.get(InteractionType.BOOKMARK.value, 0),
        "share_count": counts.get(InteractionType.SHARE.value, 0),
        "read_count": counts.get(InteractionType.READ.value, 0),
        "comment_count": comment_count,
    }


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------


@router.post("/api/articles/{article_id}/like")
def toggle_like(
    article_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Toggle like on an article.
    If already liked, removes the like. If not, adds the like.
    Guarantees at most 1 like per user per article.
    """
    article = _get_article_or_404(db, article_id)

    # Check existing like
    existing_like = (
        db.query(Interaction)
        .filter(
            Interaction.user_id == current_user.id,
            Interaction.article_id == article.id,
            Interaction.type == InteractionType.LIKE.value,
        )
        .first()
    )

    if existing_like:
        db.delete(existing_like)
        db.commit()
        counts = _get_article_counts(db, article.id)
        return {
            "status": "unliked",
            "liked": False,
            "article_id": str(article.id),
            "like_count": counts["like_count"],
        }
    else:
        new_like = Interaction(
            user_id=current_user.id,
            article_id=article.id,
            type=InteractionType.LIKE.value,
        )
        db.add(new_like)
        db.commit()
        counts = _get_article_counts(db, article.id)
        return {
            "status": "liked",
            "liked": True,
            "article_id": str(article.id),
            "like_count": counts["like_count"],
        }


@router.post("/api/articles/{article_id}/bookmark")
def toggle_bookmark(
    article_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Toggle bookmark on an article.
    If already bookmarked, removes the bookmark. If not, adds the bookmark.
    """
    article = _get_article_or_404(db, article_id)

    existing_bookmark = (
        db.query(Interaction)
        .filter(
            Interaction.user_id == current_user.id,
            Interaction.article_id == article.id,
            Interaction.type == InteractionType.BOOKMARK.value,
        )
        .first()
    )

    if existing_bookmark:
        db.delete(existing_bookmark)
        db.commit()
        counts = _get_article_counts(db, article.id)
        return {
            "status": "unbookmarked",
            "bookmarked": False,
            "article_id": str(article.id),
            "bookmark_count": counts["bookmark_count"],
        }
    else:
        new_bookmark = Interaction(
            user_id=current_user.id,
            article_id=article.id,
            type=InteractionType.BOOKMARK.value,
        )
        db.add(new_bookmark)
        db.commit()
        counts = _get_article_counts(db, article.id)
        return {
            "status": "bookmarked",
            "bookmarked": True,
            "article_id": str(article.id),
            "bookmark_count": counts["bookmark_count"],
        }


@router.post("/api/articles/{article_id}/share")
def track_share(
    article_id: str,
    payload: Optional[ShareTrackingRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Track an article share event without blocking the user."""
    article = _get_article_or_404(db, article_id)

    share_event = Interaction(
        user_id=current_user.id,
        article_id=article.id,
        type=InteractionType.SHARE.value,
    )
    db.add(share_event)
    db.commit()

    counts = _get_article_counts(db, article.id)
    return {
        "status": "shared",
        "article_id": str(article.id),
        "share_count": counts["share_count"],
    }


@router.post("/api/articles/{article_id}/read")
def track_read(
    article_id: str,
    payload: Optional[ReadTrackingRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Track article read event and time spent viewing."""
    article = _get_article_or_404(db, article_id)

    time_spent = payload.time_spent_seconds if payload else 0

    read_event = Interaction(
        user_id=current_user.id,
        article_id=article.id,
        type=InteractionType.READ.value,
        time_spent_seconds=time_spent,
    )
    db.add(read_event)
    db.commit()

    counts = _get_article_counts(db, article.id)
    return {
        "status": "read_recorded",
        "article_id": str(article.id),
        "time_spent_seconds": time_spent,
        "read_count": counts["read_count"],
    }


@router.get("/api/articles/{article_id}/interactions")
def get_interactions(
    article_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get interaction counts and user interaction status for an article."""
    article = _get_article_or_404(db, article_id)
    counts = _get_article_counts(db, article.id)

    is_liked = False
    is_bookmarked = False

    if current_user:
        user_interactions = (
            db.query(Interaction.type)
            .filter(
                Interaction.user_id == current_user.id,
                Interaction.article_id == article.id,
                Interaction.type.in_([InteractionType.LIKE.value, InteractionType.BOOKMARK.value]),
            )
            .all()
        )
        types_set = {t[0] for t in user_interactions}
        is_liked = InteractionType.LIKE.value in types_set
        is_bookmarked = InteractionType.BOOKMARK.value in types_set

    return {
        "article_id": str(article.id),
        "like_count": counts["like_count"],
        "bookmark_count": counts["bookmark_count"],
        "share_count": counts["share_count"],
        "comment_count": counts["comment_count"],
        "read_count": counts["read_count"],
        "is_liked": is_liked,
        "is_bookmarked": is_bookmarked,
    }


@router.get("/api/users/me/bookmarks")
def get_user_bookmarks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    page: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve articles bookmarked by the current user with pagination."""
    resolved_offset = offset
    if page is not None:
        resolved_offset = (page - 1) * limit

    resolved_page = (resolved_offset // limit) + 1

    query = (
        db.query(Interaction, Article)
        .join(Article, Interaction.article_id == Article.id)
        .filter(
            Interaction.user_id == current_user.id,
            Interaction.type == InteractionType.BOOKMARK.value,
        )
        .options(
            joinedload(Article.category),
            joinedload(Article.source),
            joinedload(Article.snaps),
        )
        .order_by(Interaction.created_at.desc())
    )

    total = query.count()
    items = query.offset(resolved_offset).limit(limit).all()

    bookmarked_articles: List[Dict[str, Any]] = []
    for interaction, article in items:
        snap = article.snaps[0] if (hasattr(article, "snaps") and article.snaps) else None
        cat_slug = article.category.slug if article.category else "national"
        src_name = article.source.name if article.source else "Unknown"
        src_slug = article.source.slug if article.source else "unknown"

        summary = snap.summary if snap else (article.body[:200] if article.body else "")

        bookmarked_articles.append(
            {
                "id": str(article.id),
                "article_id": str(article.id),
                "title": article.title,
                "summary": summary,
                "category": cat_slug,
                "source": src_slug,
                "source_name": src_name,
                "image_url": article.image_url or (snap.image_url if snap else ""),
                "source_url": article.source_url,
                "publish_time": article.publish_time.isoformat() if article.publish_time else None,
                "bookmarked_at": interaction.created_at.isoformat() if interaction.created_at else None,
            }
        )

    return {
        "total": total,
        "limit": limit,
        "offset": resolved_offset,
        "page": resolved_page,
        "bookmarks": bookmarked_articles,
    }
