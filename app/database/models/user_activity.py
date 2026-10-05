import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserActivityDay(Base):
    """One row per user per (Tashkent-time) day they interacted with the bot.

    Kept as day-level rows rather than a single last_seen column so the admin
    panel can tell a one-off visitor from someone who keeps coming back
    (e.g. "active on 8 different days this month")."""

    __tablename__ = "user_activity_days"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
