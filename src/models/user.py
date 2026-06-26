"""NewsSnap AI - User and UserPreference database models."""

import uuid

from sqlalchemy import JSON, Boolean, Column, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.config.settings import Language, UserRole
from src.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User accounts model."""

    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )
    name = Column(
        String,
        nullable=False,
    )
    hashed_password = Column(
        String,
        nullable=True,
    )
    role = Column(
        Enum(UserRole),
        default=UserRole.READER,
        nullable=False,
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_onboarded = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    # One-to-one relationship with UserPreference
    preferences = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserPreference(Base, TimestampMixin):
    """User language and category preferences model."""

    __tablename__ = "user_preferences"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_language = Column(
        Enum(Language),
        default=Language.ENGLISH,
        nullable=False,
    )
    secondary_language = Column(
        Enum(Language),
        nullable=True,
    )
    categories = Column(
        JSON,
        nullable=False,
        default=list,
    )

    # Back relation to User
    user = relationship(
        "User",
        back_populates="preferences",
    )
