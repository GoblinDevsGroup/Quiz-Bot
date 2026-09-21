import uuid

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class ModerationNotification(UUIDPkMixin, TimestampMixin, Base):
    """One "new quiz awaiting approval" message sent to one admin. Kept so that
    when any admin decides, the same message can be rewritten for all the
    others — otherwise their approve/reject buttons stay live and a second
    click would moderate the quiz twice."""

    __tablename__ = "moderation_notifications"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
