from typing import Optional

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin.admin_service import is_admin


class IsAdmin(BaseFilter):
    """`session` is resolved from the middleware data (DatabaseMiddleware runs
    as an update-level outer middleware, so it is always present by the time
    filters run) — it's what lets panel-added admins pass, not just the
    owners listed in ADMIN_IDS."""

    async def __call__(self, event: Message | CallbackQuery, session: Optional[AsyncSession] = None) -> bool:
        if event.from_user is None:
            return False
        return await is_admin(session, event.from_user.id)
