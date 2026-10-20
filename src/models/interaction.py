"""NewsSnap AI - Interaction and Comment database models (Issue 19).

Models for:
- User interactions: like, bookmark, share, read
- User comments on articles
"""

import uuid
from enum import Enum

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class InteractionType(str, Enum):
    """Types of user interactions."""

    LIKE = "like"
    BOOKMARK = "bookmark"
    SHARE = "share"
    READ = "read"


class Interaction(Base, TimestampMixin):
    """User interaction events model."""

    __tablename__ = "interactions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(
        String,
        nullable=False,
        index=True,
    )
    time_spent_seconds = Column(
        Integer,
        nullable=True,
        default=0,
    )

    # Relationships
    user = relationship(
        "User",
        backref="interactions",
    )
    article = relationship(
        "Article",
        back_populates="interactions",
    )


class Comment(Base, TimestampMixin):
    """User comments on articles model."""

    __tablename__ = "comments"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(
        Text,
        nullable=False,
    )

    @property
    def text(self) -> str:
        """Alias for content."""
        return self.content

    @text.setter
    def text(self, val: str):
        self.content = val

    # Relationships
    user = relationship(
        "User",
        backref="comments",
    )
    article = relationship(
        "Article",
        back_populates="comments",
    )
