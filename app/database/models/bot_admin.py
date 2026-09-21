from typing import Optional

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class BotAdmin(UUIDPkMixin, TimestampMixin, Base):
    """An admin added from inside the bot's own admin panel. These sit
    alongside — never replace — the ids in the ADMIN_IDS env var: those are
    the owners, and they stay admins even if the database is wiped, which is
    what keeps the bot from ever ending up with nobody able to manage it."""

    __tablename__ = "bot_admins"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    added_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    @property
    def label(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.full_name or str(self.telegram_user_id)
