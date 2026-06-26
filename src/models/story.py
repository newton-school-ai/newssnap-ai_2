"""NewsSnap AI - Story and StoryArticle database models."""

import uuid

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class Story(Base, TimestampMixin):
    """News story model clustering related articles."""

    __tablename__ = "stories"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    primary_article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    primary_article = relationship(
        "Article",
        foreign_keys=[primary_article_id],
        backref="primary_story",
    )


class StoryArticle(Base, TimestampMixin):
    """Junction table linking articles to clustered stories."""

    __tablename__ = "story_articles"

    story_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
