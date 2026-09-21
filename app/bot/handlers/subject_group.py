import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import SubjectGroupCB
from app.bot.keyboards.subject_group import subject_group_list_keyboard, subject_group_subject_keyboard
from app.bot.states.subject_group_states import SubjectGroupStates
from app.core.validation import is_http_url
from app.database.models import User
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.subject_group_repository import SubjectGroupRepository
from app.i18n import Translator
from app.services.admin.admin_service import is_admin

router = Router(name="subject_group")


async def _is_admin(session, telegram_id: int | None) -> bool:
    return await is_admin(session, telegram_id)


async def _send_or_edit(target, text: str, kb) -> None:
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


async def render_test_group_subjects(target, session: AsyncSession, user: User, translator: Translator) -> None:
    category_repo = CategoryRepository(session)
    subjects = await category_repo.get_canonical_subjects()
    await _send_or_edit(target, translator("test_group_choose_subject"), subject_group_subject_keyboard(user.locale, subjects))


async def render_test_group_list(target, session: AsyncSession, user: User, translator: Translator, category_id: str) -> None:
    category_repo = CategoryRepository(session)
    category = await category_repo.get_by_id(uuid.UUID(category_id))
    if category is None:
        await _send_or_edit(target, translator("quiz_not_found"), subject_group_subject_keyboard(user.locale, []))
        return

    group_repo = SubjectGroupRepository(session)
    groups = await group_repo.list_by_category(category.id)
    viewer_is_admin = await _is_admin(session, user.telegram_user_id)

    icon = category.icon or ""
    heading = f"{icon} {category.localized_name(user.locale)}".strip()
    body = translator("test_group_list_title", subject=heading) if groups else translator("test_group_empty", subject=heading)
    await _send_or_edit(target, body, subject_group_list_keyboard(user.locale, category_id, groups, viewer_is_admin))


@router.callback_query(SubjectGroupCB.filter(F.action == "subjects"))
async def back_to_subjects(callback: CallbackQuery, session: AsyncSession, user: User, translator: Translator) -> None:
    await render_test_group_subjects(callback, session, user, translator)
    await callback.answer()


@router.callback_query(SubjectGroupCB.filter(F.action == "subject"))
async def choose_subject(
    callback: CallbackQuery, callback_data: SubjectGroupCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    await render_test_group_list(callback, session, user, translator, callback_data.category_id)
    await callback.answer()


@router.callback_query(SubjectGroupCB.filter(F.action == "add_prompt"))
async def prompt_add_group(
    callback: CallbackQuery,
    callback_data: SubjectGroupCB,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    translator: Translator,
) -> None:
    if not await _is_admin(session, user.telegram_user_id):
        await callback.answer()
        return
    await state.set_state(SubjectGroupStates.awaiting_group_link)
    await state.update_data(category_id=callback_data.category_id)
    await callback.message.answer(translator("test_group_prompt_link"))
    await callback.answer()


@router.message(SubjectGroupStates.awaiting_group_link)
async def apply_add_group(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    if not await _is_admin(session, user.telegram_user_id):
        await state.clear()
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    link = parts[0] if parts else ""
    title = parts[1].strip() if len(parts) > 1 else None
    if not is_http_url(link):
        await message.answer(translator("test_group_invalid_link"))
        return

    data = await state.get_data()
    category_id = data.get("category_id")
    await state.clear()

    group_repo = SubjectGroupRepository(session)
    await group_repo.add(uuid.UUID(category_id), invite_link=link, title=title, added_by_telegram_id=user.telegram_user_id)

    await message.answer(translator("test_group_added"))
    await render_test_group_list(message, session, user, translator, category_id)


@router.callback_query(SubjectGroupCB.filter(F.action == "delete"))
async def delete_group(
    callback: CallbackQuery, callback_data: SubjectGroupCB, session: AsyncSession, user: User, translator: Translator
) -> None:
    if not await _is_admin(session, user.telegram_user_id):
        await callback.answer()
        return

    group_repo = SubjectGroupRepository(session)
    group = await group_repo.get_by_id(uuid.UUID(callback_data.group_id))
    if group is None:
        await callback.answer()
        return

    category_id = str(group.category_id)
    await group_repo.delete(group)

    await callback.answer(translator("test_group_deleted"))
    await render_test_group_list(callback, session, user, translator, category_id)
