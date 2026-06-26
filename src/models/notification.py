"""NewsSnap AI - Notification database model."""

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    """User notifications model."""

    __tablename__ = "notifications"

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
    title = Column(
        String,
        nullable=False,
    )
    body = Column(
        String,
        nullable=False,
    )
    is_read = Column(
        Boolean,
        default=False,
        nullable=False,
    )
    type = Column(
        String,
        nullable=False,
    )

    # Relationships
    user = relationship(
        "User",
        backref="notifications",
    )
