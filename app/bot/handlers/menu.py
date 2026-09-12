from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import LanguageCB, MenuCB
from app.bot.keyboards.common import language_keyboard
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.keyboards.profile import create_method_keyboard, profile_keyboard
from app.database.models import User
from app.i18n import Translator
from app.services.statistics.statistics_service import StatisticsService
from app.services.users.user_service import UserService

router = Router(name="menu")


@router.callback_query(MenuCB.filter(F.action == "main"))
async def show_main_menu(callback: CallbackQuery, state: FSMContext, user: User, translator: Translator) -> None:
    await state.clear()
    # ReplyKeyboardMarkup cannot be attached via edit_text (Telegram API only
    # allows InlineKeyboardMarkup there), so send a fresh message instead.
    await callback.message.answer(
        translator("start_welcome", name=user.display_name), reply_markup=main_menu_keyboard(user.locale)
    )
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "language"))
async def show_language_menu(callback: CallbackQuery, translator: Translator) -> None:
    await callback.message.edit_text(translator("choose_language"), reply_markup=language_keyboard())
    await callback.answer()


@router.callback_query(LanguageCB.filter())
async def set_language(
    callback: CallbackQuery, callback_data: LanguageCB, session: AsyncSession, user: User
) -> None:
    user_service = UserService(session)
    await user_service.set_locale(user, callback_data.code)
    translator = Translator(callback_data.code)
    await callback.message.edit_text(translator("language_set"))
    await callback.message.answer(
        translator("start_welcome", name=user.display_name), reply_markup=main_menu_keyboard(callback_data.code)
    )
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "create_quiz"))
async def show_create_menu(callback: CallbackQuery, translator: Translator, user: User) -> None:
    await callback.message.edit_text(translator("create_method_prompt"), reply_markup=create_method_keyboard(user.locale))
    await callback.answer()


async def build_profile_text(session: AsyncSession, user: User, translator: Translator) -> str:
    stats_service = StatisticsService(session)
    stats = await stats_service.get_user_statistics(user.id)
    return translator("profile_title", name=user.display_name) + "\n\n" + translator(
        "profile_stats",
        created=stats.quizzes_created,
        completed=stats.quizzes_completed,
        points=stats.total_points,
        rating=stats.rating,
    )


@router.callback_query(MenuCB.filter(F.action == "profile"))
async def show_profile(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    text = await build_profile_text(session, user, translator)
    await callback.message.edit_text(text, reply_markup=profile_keyboard(user.locale))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "help"))
async def show_help(callback: CallbackQuery, translator: Translator, user: User) -> None:
    from app.bot.keyboards.main_menu import back_to_main_keyboard

    await callback.message.edit_text(translator("help_text"), reply_markup=back_to_main_keyboard(user.locale))
    await callback.answer()


@router.callback_query(MenuCB.filter(F.action == "leaderboard"))
async def show_leaderboard(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    from app.bot.keyboards.main_menu import back_to_main_keyboard
    from app.database.repositories.user_repository import UserRepository

    stats_service = StatisticsService(session)
    top = await stats_service.leaderboard(10)
    user_repo = UserRepository(session)

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 Global Leaderboard\n"]
    for idx, stat in enumerate(top):
        u = await user_repo.get_by_id(stat.user_id)
        medal = medals[idx] if idx < 3 else f"{idx + 1}."
        name = u.display_name if u else "?"
        lines.append(f"{medal} {name} — {stat.total_points}")

    if not top:
        lines.append("—")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_to_main_keyboard(user.locale))
    await callback.answer()
