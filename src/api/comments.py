"""NewsSnap AI - Comments API Router (Issue 19).

Endpoints:
- POST /api/articles/{article_id}/comments: Create comment with rate limiting (max 100/day)
- GET /api/articles/{article_id}/comments: List paginated comments for an article
- DELETE /api/articles/{article_id}/comments/{comment_id}: Delete own comment
- DELETE /api/comments/{comment_id}: Delete own comment (direct route)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.middleware import get_current_user
from src.config.database import get_db
from src.models.article import Article
from src.models.interaction import Comment
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["comments"])

MAX_COMMENTS_PER_DAY = 100


# ------------------------------------------------------------------------------
# Request Schemas
# ------------------------------------------------------------------------------


class CreateCommentRequest(BaseModel):
    content: Optional[str] = Field(default=None, description="Comment content")
    text: Optional[str] = Field(default=None, description="Alternative key for comment content")

    @model_validator(mode="after")
    def validate_content(self) -> "CreateCommentRequest":
        resolved_text = (self.content or self.text or "").strip()
        if not resolved_text:
            raise ValueError("Comment text cannot be empty")
        self.content = resolved_text
        self.text = resolved_text
        return self


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


def _check_comment_rate_limit(db: Session, user_id: uuid.UUID) -> None:
    """Enforce maximum 100 comments per user per 24-hour day."""
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    daily_count = (
        db.query(func.count(Comment.id)).filter(Comment.user_id == user_id, Comment.created_at >= one_day_ago).scalar()
        or 0
    )

    if daily_count >= MAX_COMMENTS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: Maximum {MAX_COMMENTS_PER_DAY} comments per day",
        )


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------


@router.post("/api/articles/{article_id}/comments")
def create_comment(
    article_id: str,
    payload: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create a new comment on an article.
    Rate limited to max 100 comments per user per day.
    """
    article = _get_article_or_404(db, article_id)
    _check_comment_rate_limit(db, current_user.id)

    new_comment = Comment(
        user_id=current_user.id,
        article_id=article.id,
        content=payload.content,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return {
        "id": str(new_comment.id),
        "article_id": str(article.id),
        "user_id": str(current_user.id),
        "user_name": current_user.name,
        "content": new_comment.content,
        "text": new_comment.content,
        "created_at": new_comment.created_at.isoformat() if new_comment.created_at else None,
    }


@router.get("/api/articles/{article_id}/comments")
def list_comments(
    article_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    page: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """List paginated comments for an article."""
    article = _get_article_or_404(db, article_id)

    resolved_offset = offset
    if page is not None:
        resolved_offset = (page - 1) * limit

    resolved_page = (resolved_offset // limit) + 1

    query = (
        db.query(Comment)
        .filter(Comment.article_id == article.id)
        .options(joinedload(Comment.user))
        .order_by(Comment.created_at.desc())
    )

    total = query.count()
    comments = query.offset(resolved_offset).limit(limit).all()

    formatted_comments: List[Dict[str, Any]] = []
    for c in comments:
        user_name = c.user.name if c.user and hasattr(c.user, "name") else "Anonymous"
        formatted_comments.append(
            {
                "id": str(c.id),
                "article_id": str(c.article_id),
                "user_id": str(c.user_id),
                "user_name": user_name,
                "content": c.content,
                "text": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        )

    return {
        "article_id": str(article.id),
        "total": total,
        "limit": limit,
        "offset": resolved_offset,
        "page": resolved_page,
        "comments": formatted_comments,
    }


def _delete_comment_logic(
    db: Session,
    comment_id: str,
    current_user: User,
    article_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal logic to delete a comment ensuring user owns it."""
    try:
        comment_uuid = uuid.UUID(str(comment_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid comment ID format")

    comment = db.query(Comment).filter(Comment.id == comment_uuid).first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if article_id:
        try:
            art_uuid = uuid.UUID(str(article_id))
            if comment.article_id != art_uuid:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment does not belong to article")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid article ID format")

    # Authorize deletion: only comment owner or admin can delete
    is_admin = getattr(current_user, "role", None) == "admin"
    if comment.user_id != current_user.id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete another user's comment",
        )

    db.delete(comment)
    db.commit()

    return {
        "status": "deleted",
        "comment_id": str(comment_uuid),
    }


@router.delete("/api/articles/{article_id}/comments/{comment_id}")
def delete_article_comment(
    article_id: str,
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a user's own comment under an article."""
    return _delete_comment_logic(db, comment_id, current_user, article_id=article_id)


@router.delete("/api/comments/{comment_id}")
def delete_comment_direct(
    comment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a user's own comment by comment ID directly."""
    return _delete_comment_logic(db, comment_id, current_user)
