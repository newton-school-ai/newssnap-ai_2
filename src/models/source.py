"""NewsSnap AI - Source database model."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from src.config.settings import Language, ScrapeType
from src.models.base import Base, TimestampMixin


class Source(Base, TimestampMixin):
    """News source registry model."""

    __tablename__ = "sources"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )
    name = Column(
        String,
        nullable=False,
    )
    base_url = Column(
        String,
        nullable=False,
    )
    article_list_url = Column(
        String,
        nullable=False,
    )
    language = Column(
        Enum(Language),
        default=Language.ENGLISH,
        nullable=False,
    )
    scrape_type = Column(
        Enum(ScrapeType),
        default=ScrapeType.PLAYWRIGHT,
        nullable=False,
    )
    rate_limit_seconds = Column(
        Integer,
        default=2,
        nullable=False,
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_scrape_time = Column(
        DateTime,
        nullable=True,
    )
    success_count = Column(
        Integer,
        default=0,
        nullable=False,
    )
    error_count = Column(
        Integer,
        default=0,
        nullable=False,
    )
    is_healthy = Column(
        Boolean,
        default=True,
        nullable=False,
    )
