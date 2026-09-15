import uuid
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class SubjectGroup(UUIDPkMixin, TimestampMixin, Base):
    """A Telegram group an admin has attached to a subject (category) —
    shown to users under "🧪 Test guruh" so they can join a group dedicated
    to practicing that subject. A category can have several of these."""

    __tablename__ = "subject_groups"

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invite_link: Mapped[str] = mapped_column(String(512), nullable=False)
    added_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    category: Mapped["Category"] = relationship(back_populates="subject_groups")
