"""NewsSnap AI - Interaction and Comment database models."""

import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


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
    )
    time_spent_seconds = Column(
        Integer,
        nullable=True,
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
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(
        Text,
        nullable=False,
    )

    # Relationships
    user = relationship(
        "User",
        backref="comments",
    )
    article = relationship(
        "Article",
        back_populates="comments",
    )
