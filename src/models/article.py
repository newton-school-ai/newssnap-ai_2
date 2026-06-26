"""NewsSnap AI - Article and ArticleEmbedding database models."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from src.config.settings import Language
from src.models.base import Base, TimestampMixin


class Article(Base, TimestampMixin):
    """News articles scraped from sources."""

    __tablename__ = "articles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title = Column(
        String,
        nullable=False,
    )
    body = Column(
        Text,
        nullable=False,
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    language = Column(
        Enum(Language),
        default=Language.ENGLISH,
        nullable=False,
        index=True,
    )
    source_url = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )
    image_url = Column(
        String,
        nullable=True,
    )
    publish_time = Column(
        DateTime,
        nullable=False,
        index=True,
    )
    author = Column(
        String,
        nullable=True,
    )
    is_duplicate = Column(
        Boolean,
        default=False,
        nullable=False,
    )
    primary_article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="SET NULL"),
        nullable=True,
    )
    story_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stories.id", ondelete="SET NULL"),
        nullable=True,
    )
    quality_score = Column(
        Float,
        nullable=True,
    )

    # Relationships
    source = relationship(
        "Source",
        backref="articles",
    )
    category = relationship(
        "Category",
        backref="articles",
    )
    embedding = relationship(
        "ArticleEmbedding",
        back_populates="article",
        uselist=False,
        cascade="all, delete-orphan",
    )
    snaps = relationship(
        "Snap",
        back_populates="article",
        cascade="all, delete-orphan",
    )
    comments = relationship(
        "Comment",
        back_populates="article",
        cascade="all, delete-orphan",
    )
    interactions = relationship(
        "Interaction",
        back_populates="article",
        cascade="all, delete-orphan",
    )


class ArticleEmbedding(Base, TimestampMixin):
    """Article dense vector embeddings."""

    __tablename__ = "article_embeddings"

    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding = Column(
        ARRAY(Float),
        nullable=False,
    )

    # Relationship
    article = relationship(
        "Article",
        back_populates="embedding",
    )
