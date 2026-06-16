import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            "posting_frequency IS NULL OR posting_frequency >= 0",
            name="ck_user_profiles_posting_frequency_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(120))
    company: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    expertise: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}", nullable=False
    )
    tone: Mapped[str | None] = mapped_column(String(120))
    audience: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}", nullable=False
    )
    posting_frequency: Mapped[int | None] = mapped_column(Integer)
    content_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}", nullable=False
    )
    raw_source: Mapped[str | None] = mapped_column(Text)
    writing_samples: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="profile")
