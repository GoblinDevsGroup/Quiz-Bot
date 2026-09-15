from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import SubscriptionCB
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.keyboards.required_channel import subscription_gate_keyboard
from app.database.models import User
from app.database.repositories.required_channel_repository import RequiredChannelRepository
from app.i18n import Translator
from app.services.subscription.subscription_service import get_missing_channels

router = Router(name="subscription_gate")


@router.callback_query(SubscriptionCB.filter(F.action == "check"))
async def check_subscription(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    repo = RequiredChannelRepository(session)
    channels = await repo.list_active()
    missing = await get_missing_channels(callback.bot, channels, user.telegram_user_id)

    if missing:
        try:
            await callback.message.edit_reply_markup(reply_markup=subscription_gate_keyboard(user.locale, missing))
        except Exception:
            pass
        await callback.answer(translator("subscribe_still_missing"), show_alert=True)
        return

    await callback.answer(translator("subscribe_confirmed_toast"))
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        translator("start_welcome", name=user.display_name), reply_markup=main_menu_keyboard(user.locale)
    )
