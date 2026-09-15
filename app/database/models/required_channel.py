from typing import Optional

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class RequiredChannel(UUIDPkMixin, TimestampMixin, Base):
    """A channel an admin has marked mandatory — every non-admin user must be
    a member of every active row here before the bot will respond to them
    in a private chat (checked via getChatMember, so the bot must itself be
    an admin of the channel)."""

    __tablename__ = "required_channels"

    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    invite_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    added_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
