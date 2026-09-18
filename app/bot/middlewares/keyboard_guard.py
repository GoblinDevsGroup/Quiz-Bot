from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.client.bot import Bot
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType
from aiogram.types import ReplyKeyboardMarkup

from app.core.logging import get_logger

logger = get_logger(__name__)


class GroupKeyboardGuardMiddleware(BaseRequestMiddleware):
    """Last-resort safety net: a persistent ReplyKeyboardMarkup (the private
    main menu) must never reach a group/supergroup/channel — Telegram shows
    it to every member, not just the one the bot meant to answer, and it
    keeps sticking around for the whole chat until explicitly removed.
    Per-handler chat-type checks already guard every known call site, but a
    single missed one leaks the menu to everyone in that group forever, so
    this strips it at the API-call boundary regardless of where it came from.
    Telegram chat ids are negative for groups/supergroups/channels and
    positive for private chats/users, so that sign alone is enough here."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        chat_id = getattr(method, "chat_id", None)
        reply_markup = getattr(method, "reply_markup", None)
        if isinstance(chat_id, int) and chat_id < 0 and isinstance(reply_markup, ReplyKeyboardMarkup):
            logger.warning("blocked_group_reply_keyboard", chat_id=chat_id, method=method.__class__.__name__)
            method.reply_markup = None
        return await make_request(bot, method)
