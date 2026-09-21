import html

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.feedback_states import FeedbackStates
from app.database.models import User
from app.i18n import Translator
from app.services.admin.admin_service import all_admin_ids

router = Router(name="feedback")


async def open_feedback(message: Message, state: FSMContext, translator: Translator) -> None:
    await state.set_state(FeedbackStates.awaiting_text)
    await message.answer(translator("feedback_prompt"))


@router.message(FeedbackStates.awaiting_text)
async def submit_feedback(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator
) -> None:
    await state.clear()
    text = (message.text or "").strip()
    if not text:
        await message.answer(translator("feedback_empty"))
        return

    username = f"@{message.from_user.username}" if message.from_user.username else user.display_name
    admin_text = (
        f"🛎 Yangi shikoyat/taklif\n\n"
        f"👤 {html.escape(username)} (tg_id={user.telegram_user_id})\n\n"
        f"{html.escape(text)}"
    )
    for admin_id in await all_admin_ids(session):
        try:
            await message.bot.send_message(admin_id, admin_text, parse_mode=None)
        except Exception:
            pass

    await message.answer(translator("feedback_thanks"))
