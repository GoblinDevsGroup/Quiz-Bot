from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import TelegramObject

from app.core.logging import get_logger
from app.i18n import Translator

logger = get_logger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Global safety net: never leak stack traces to users, log details internally."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                # Harmless: happens when a user re-taps a button whose content
                # (text + keyboard) is identical to what's already on screen.
                # Nothing needs to change, so just ack the tap silently.
                # `event` here is the Update object (this runs as an
                # update-level outer middleware), so its .callback_query
                # attribute is what we need, not `event` itself.
                callback_query = getattr(event, "callback_query", None)
                if callback_query:
                    try:
                        await callback_query.answer()
                    except Exception:
                        pass
                return None
            logger.exception("telegram_bad_request", error=str(exc))
            await self._notify_user_of_error(event, data)
            return None
        except Exception as exc:
            logger.exception("unhandled_handler_error", error=str(exc))
            await self._notify_user_of_error(event, data)
            return None

    @staticmethod
    async def _notify_user_of_error(event: TelegramObject, data: Dict[str, Any]) -> None:
        translator = data.get("translator") or Translator("uz")
        message = getattr(event, "message", None) or getattr(event, "callback_query", None)
        try:
            if hasattr(message, "answer"):
                await message.answer(translator("db_error_generic"))
        except Exception:
            pass
