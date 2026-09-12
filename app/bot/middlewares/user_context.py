from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.core.logging import get_logger
from app.i18n import Translator
from app.services.users.user_service import UserService

logger = get_logger(__name__)


class UserContextMiddleware(BaseMiddleware):
    """Resolves/creates the local User row for every incoming update and
    injects it plus a bound translator into handler data. Also enforces bans."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        session = data["session"]
        user_service = UserService(session)
        user = await user_service.get_or_create_from_telegram(tg_user)

        if user.is_banned:
            translator = Translator(user.locale)
            bot = data.get("bot")
            chat = getattr(event, "message", None)
            if bot and chat:
                try:
                    await bot.send_message(tg_user.id, translator("banned_user"))
                except Exception:
                    pass
            return None

        data["user"] = user
        data["translator"] = Translator(user.locale)
        return await handler(event, data)
