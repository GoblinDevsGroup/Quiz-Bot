import uuid
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MessageOriginHiddenUser, MessageOriginUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.commands import grant_admin_commands, revoke_admin_commands
from app.bot.filters.admin_filter import IsAdmin
from app.bot.keyboards.admin import ADMINS_SHOWN_LIMIT, admin_admins_keyboard
from app.bot.keyboards.callback_data import AdminManageCB
from app.bot.states.admin_states import AdminStates
from app.database.repositories.bot_admin_repository import BotAdminRepository
from app.database.repositories.user_repository import UserRepository
from app.services.admin.admin_service import invalidate_cache, is_admin, owner_ids

router = Router(name="bot_admins")
router.message.filter(IsAdmin())


async def _is_admin_callback(callback: CallbackQuery, session: AsyncSession) -> bool:
    return callback.from_user is not None and await is_admin(session, callback.from_user.id)


async def _render_admins(target, session: AsyncSession) -> None:
    repo = BotAdminRepository(session)
    admins = await repo.list_all()
    owners = sorted(owner_ids())

    lines = [
        "👮 Bot adminlari",
        "",
        f"👑 Asosiy adminlar: {len(owners)} ta (ular o'chirilmaydi)",
        f"👮 Qo'shilgan adminlar: {len(admins)} ta",
    ]
    if len(admins) > ADMINS_SHOWN_LIMIT:
        lines.append("")
        lines.append(f"(Ro'yxatda faqat birinchi {ADMINS_SHOWN_LIMIT} tasi ko'rsatilgan.)")
    text = "\n".join(lines)
    kb = admin_admins_keyboard(owners, admins)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode=None)
    else:
        await target.answer(text, reply_markup=kb, parse_mode=None)


@router.callback_query(AdminManageCB.filter(F.action == "noop"))
async def noop_admin_label(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(AdminManageCB.filter(F.action == "list"))
async def list_admins(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _is_admin_callback(callback, session):
        await callback.answer()
        return
    await _render_admins(callback, session)
    await callback.answer()


@router.callback_query(AdminManageCB.filter(F.action == "add_prompt"))
async def prompt_add_admin(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _is_admin_callback(callback, session):
        await callback.answer()
        return
    await state.set_state(AdminStates.awaiting_new_admin)
    await callback.message.answer(
        "Yangi adminni quyidagi usullardan biri bilan yuboring:\n"
        "• Uning istalgan xabarini bu yerga forward qiling, YOKI\n"
        "• Telegram ID sini yuboring (masalan: 123456789), YOKI\n"
        "• @username ini yuboring (u avval botga /start bosgan bo'lishi kerak)\n\n"
        "(Bekor qilish uchun /cancel yuboring)",
        parse_mode=None,
    )
    await callback.answer()


async def _resolve_target(message: Message, session: AsyncSession) -> tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    """Returns (telegram_id, username, full_name, error_text)."""
    origin = message.forward_origin
    if isinstance(origin, MessageOriginUser):
        sender = origin.sender_user
        return sender.id, sender.username, sender.full_name, None
    if isinstance(origin, MessageOriginHiddenUser):
        # The sender hides their account when forwarding, so Telegram gives us
        # a name and no id — nothing we can key an admin row on.
        return None, None, None, (
            "❌ Bu foydalanuvchi forward xabarlarida o'z akkountini yashirgan.\n"
            "Uning Telegram ID sini yoki @username ini yuboring."
        )

    text = (message.text or "").strip()
    if not text:
        return None, None, None, "❌ Foydalanuvchini forward qiling yoki ID/@username yuboring."

    if text.lstrip("-").isdigit():
        telegram_id = int(text)
        if telegram_id <= 0:
            return None, None, None, "❌ Noto'g'ri Telegram ID."
        # The bot's own user row is optional here: an id typed by hand may
        # belong to someone who hasn't started the bot yet, and that's fine —
        # they become an admin as soon as they do.
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is not None:
            return telegram_id, user.username, user.display_name, None
        return telegram_id, None, None, None

    handle = text.removeprefix("https://t.me/").removeprefix("http://t.me/").removeprefix("t.me/").removeprefix("@").strip("/")
    if not handle:
        return None, None, None, "❌ Foydalanuvchini forward qiling yoki ID/@username yuboring."

    # Telegram gives bots no way to look up an arbitrary @username, so this
    # can only find people already known to the bot.
    user_repo = UserRepository(session)
    matches = [u for u in await user_repo.search_by_username(handle) if (u.username or "").lower() == handle.lower()]
    if not matches:
        return None, None, None, (
            f"❌ @{handle} topilmadi. U avval botga /start bosishi kerak,\n"
            "yoki uning xabarini forward qiling / Telegram ID sini yuboring."
        )
    user = matches[0]
    return user.telegram_user_id, user.username, user.display_name, None


@router.message(AdminStates.awaiting_new_admin)
async def apply_add_admin(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()

    telegram_id, username, full_name, error = await _resolve_target(message, session)
    if error is not None or telegram_id is None:
        await message.answer(error or "❌ Foydalanuvchi aniqlanmadi.", parse_mode=None)
        return

    label = f"@{username}" if username else (full_name or str(telegram_id))

    if telegram_id in owner_ids():
        await message.answer(f"ℹ️ {label} allaqachon asosiy admin.", parse_mode=None)
        await _render_admins(message, session)
        return

    repo = BotAdminRepository(session)
    if await repo.get_by_telegram_id(telegram_id) is not None:
        await message.answer(f"ℹ️ {label} allaqachon admin.", parse_mode=None)
        await _render_admins(message, session)
        return

    await repo.add(
        telegram_id,
        username=username,
        full_name=full_name,
        added_by_telegram_id=message.from_user.id if message.from_user else None,
    )
    invalidate_cache()

    await grant_admin_commands(message.bot, telegram_id)
    try:
        await message.bot.send_message(
            telegram_id,
            "🛠 Sizga bot admin huquqlari berildi.\n\nAdmin panelni ochish uchun /admin yuboring.",
            parse_mode=None,
        )
    except Exception:
        # Not every new admin has an open chat with the bot yet — the rights
        # still apply, they just won't see this heads-up.
        pass

    await message.answer(f"✅ {label} admin qilib qo'shildi.", parse_mode=None)
    await _render_admins(message, session)


@router.callback_query(AdminManageCB.filter(F.action == "delete"))
async def delete_admin(callback: CallbackQuery, callback_data: AdminManageCB, session: AsyncSession) -> None:
    if not await _is_admin_callback(callback, session):
        await callback.answer()
        return

    repo = BotAdminRepository(session)
    admin = await repo.get_by_id(uuid.UUID(callback_data.admin_id))
    if admin is None:
        await callback.answer("Admin topilmadi.", show_alert=True)
        await _render_admins(callback, session)
        return

    telegram_id = admin.telegram_user_id
    label = admin.label
    await repo.delete(admin)
    invalidate_cache()

    await revoke_admin_commands(callback.bot, telegram_id)
    try:
        await callback.bot.send_message(telegram_id, "ℹ️ Sizning bot admin huquqlaringiz bekor qilindi.", parse_mode=None)
    except Exception:
        pass

    await callback.answer(f"🗑 {label} o'chirildi.")
    await _render_admins(callback, session)
