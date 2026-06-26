"""NewsSnap AI - Category database model."""

from sqlalchemy import Boolean, Column, Integer, String

from src.models.base import Base, TimestampMixin


class Category(Base, TimestampMixin):
    """News categories model."""

    __tablename__ = "categories"

    id = Column(
        Integer,
        primary_key=True,
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
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
