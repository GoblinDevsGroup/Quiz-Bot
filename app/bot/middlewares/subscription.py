from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.keyboards.required_channel import subscription_gate_keyboard
from app.core.config import settings
from app.database.repositories.required_channel_repository import RequiredChannelRepository
from app.i18n import Translator
from app.services.subscription.subscription_service import get_missing_channels


class SubscriptionMiddleware(BaseMiddleware):
    """Blocks every non-admin private-chat interaction until the user has
    joined every active RequiredChannel. Only applies to Message/CallbackQuery
    in private chats — group activity (test groups, group quizzes) and the
    subscription-check callback itself are left untouched."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        message = event if isinstance(event, Message) else None
        callback = event if isinstance(event, CallbackQuery) else None
        if message is None and callback is None:
            return await handler(event, data)

        # The "I've subscribed, check again" button re-verifies itself —
        # never gate it, or a still-not-subscribed user could never dismiss it.
        if callback is not None and (callback.data or "").startswith("sub:"):
            return await handler(event, data)

        chat = message.chat if message is not None else (callback.message.chat if callback.message else None)
        if chat is None or chat.type != "private":
            return await handler(event, data)

        user = data.get("user")
        if user is None or user.telegram_user_id in settings.admin_id_list:
            return await handler(event, data)

        session = data["session"]
        bot = data["bot"]
        translator: Translator = data.get("translator") or Translator(user.locale)

        repo = RequiredChannelRepository(session)
        channels = await repo.list_active()
        if not channels:
            return await handler(event, data)

        missing = await get_missing_channels(bot, channels, user.telegram_user_id)
        if not missing:
            return await handler(event, data)

        text = translator("subscribe_required_intro")
        kb = subscription_gate_keyboard(user.locale, missing)
        if message is not None:
            await message.answer(text, reply_markup=kb)
        else:
            await callback.answer()
            await callback.message.answer(text, reply_markup=kb)
        return None
