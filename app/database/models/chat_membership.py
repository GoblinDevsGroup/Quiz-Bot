from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class BotChatMembership(TimestampMixin, Base):
    """Tracks which chats the bot is currently a member of. Telegram's Bot
    API has no "list my chats" endpoint, so this is populated entirely from
    my_chat_member updates (fired whenever the bot's own status in a chat
    changes: added, promoted, removed, etc.)."""

    __tablename__ = "bot_chat_memberships"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chat_type: Mapped[str] = mapped_column(String(32), nullable=False)
    member_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
