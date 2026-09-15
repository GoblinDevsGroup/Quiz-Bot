import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MessageOriginChannel
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin_filter import IsAdmin
from app.bot.keyboards.callback_data import RequiredChannelCB
from app.bot.keyboards.required_channel import admin_channels_keyboard
from app.bot.states.required_channel_states import RequiredChannelStates
from app.core.config import settings
from app.database.repositories.required_channel_repository import RequiredChannelRepository

router = Router(name="required_channel")
router.message.filter(IsAdmin())


def _is_admin_callback(callback: CallbackQuery) -> bool:
    return callback.from_user is not None and callback.from_user.id in settings.admin_id_list


async def _render_channels(target, session: AsyncSession) -> None:
    repo = RequiredChannelRepository(session)
    channels = await repo.list_all()
    text = "📢 Majburiy obuna kanallari:" if channels else "📢 Hozircha majburiy obuna kanali qo'shilmagan."
    kb = admin_channels_keyboard(channels)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(RequiredChannelCB.filter(F.action == "list"))
async def list_channels(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await _render_channels(callback, session)
    await callback.answer()


@router.callback_query(RequiredChannelCB.filter(F.action == "add_prompt"))
async def prompt_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    await state.set_state(RequiredChannelStates.awaiting_channel)
    await callback.message.answer(
        "Kanalni yuboring:\n"
        "• Kanaldagi istalgan postni bu yerga forward qiling, YOKI\n"
        "• Kanal usernameni yuboring (masalan: @mychannel)\n\n"
        "Bot o'sha kanalda ADMIN bo'lishi shart (a'zolikni tekshirish uchun).\n\n"
        "(Bekor qilish uchun /cancel yuboring)"
    )
    await callback.answer()


@router.message(RequiredChannelStates.awaiting_channel)
async def apply_add_channel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()

    bot = message.bot
    chat_id = None
    title = None
    username = None

    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        forwarded_chat = origin.chat
        chat_id = forwarded_chat.id
        title = forwarded_chat.title
        username = forwarded_chat.username
    else:
        text = (message.text or "").strip()
        handle = text.removeprefix("https://t.me/").removeprefix("http://t.me/").removeprefix("t.me/").removeprefix("@").strip("/")
        if not handle:
            await message.answer("❌ Kanalni forward qiling yoki @username yuboring.")
            return
        try:
            chat = await bot.get_chat(f"@{handle}")
        except Exception as exc:
            await message.answer(f"❌ Kanal topilmadi: {exc}")
            return
        chat_id = chat.id
        title = chat.title
        username = chat.username

    # Confirm the bot can actually check membership here — without admin
    # rights getChatMember fails for every user, which would silently break
    # the gate for this channel later.
    try:
        await bot.get_chat_member(chat_id, message.from_user.id)
    except Exception as exc:
        await message.answer(
            f"⚠️ Botni ushbu kanalga ADMIN qilib qo'shing, so'ngra qaytadan urinib ko'ring.\n\nXatolik: {exc}"
        )
        return

    invite_link = None
    if not username:
        try:
            invite_link = await bot.export_chat_invite_link(chat_id)
        except Exception:
            invite_link = None

    repo = RequiredChannelRepository(session)
    existing = await repo.get_by_chat_id(chat_id)
    if existing is not None:
        await message.answer("ℹ️ Bu kanal allaqachon ro'yxatda.")
        await _render_channels(message, session)
        return

    await repo.add(chat_id, title=title, username=username, invite_link=invite_link, added_by_telegram_id=message.from_user.id)
    await message.answer(f"✅ \"{title}\" kanali majburiy obunaga qo'shildi.")
    await _render_channels(message, session)


@router.callback_query(RequiredChannelCB.filter(F.action == "delete"))
async def delete_channel(callback: CallbackQuery, callback_data: RequiredChannelCB, session: AsyncSession) -> None:
    if not _is_admin_callback(callback):
        await callback.answer()
        return
    repo = RequiredChannelRepository(session)
    channel = await repo.get_by_id(uuid.UUID(callback_data.channel_id))
    if channel is not None:
        await repo.delete(channel)
    await callback.answer("🗑 O'chirildi.")
    await _render_channels(callback, session)
