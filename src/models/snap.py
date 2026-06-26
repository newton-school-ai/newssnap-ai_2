"""NewsSnap AI - Snap and SnapTranslation database models."""

import uuid

from sqlalchemy import Column, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.settings import Language
from src.models.base import Base, TimestampMixin


class Snap(Base, TimestampMixin):
    """News snap model containing processed summary card metadata."""

    __tablename__ = "snaps"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    language = Column(
        Enum(Language),
        default=Language.ENGLISH,
        nullable=False,
        index=True,
    )
    summary = Column(
        Text,
        nullable=False,
    )
    image_url = Column(
        String,
        nullable=True,
    )

    # Relationships
    article = relationship(
        "Article",
        back_populates="snaps",
    )
    translations = relationship(
        "SnapTranslation",
        back_populates="snap",
        cascade="all, delete-orphan",
    )


class SnapTranslation(Base, TimestampMixin):
    """Translated versions of news snaps."""

    __tablename__ = "snap_translations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    snap_id = Column(
        UUID(as_uuid=True),
        ForeignKey("snaps.id", ondelete="CASCADE"),
        nullable=False,
    )
    language = Column(
        Enum(Language),
        nullable=False,
    )
    summary = Column(
        Text,
        nullable=False,
    )

    # Relationships
    snap = relationship(
        "Snap",
        back_populates="translations",
    )
