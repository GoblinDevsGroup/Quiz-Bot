from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.manual_creation import grade_keyboard, parse_grade_choice, parse_subject_choice, subject_keyboard
from app.bot.keyboards.profile import create_method_keyboard
from app.bot.states.create_states import CreateQuizStates
from app.database.models import User
from app.database.repositories.category_repository import CategoryRepository
from app.i18n import Translator

router = Router(name="create_quiz")


@router.message(CreateQuizStates.choosing_subject)
async def set_create_subject(message: Message, state: FSMContext, session: AsyncSession, translator: Translator) -> None:
    name_uz = parse_subject_choice((message.text or "").strip())
    if name_uz is None:
        await message.answer(translator("manual_choose_subject"), reply_markup=subject_keyboard())
        return

    category_repo = CategoryRepository(session)
    subjects = await category_repo.get_canonical_subjects()
    category = next((c for c in subjects if c.name_uz == name_uz), None)
    if category is None:
        await message.answer(translator("manual_choose_subject"), reply_markup=subject_keyboard())
        return

    await state.update_data(category_id=str(category.id), subject_name=category.name_uz)
    await state.set_state(CreateQuizStates.choosing_grade)
    await message.answer(translator("manual_choose_grade"), reply_markup=grade_keyboard())


@router.message(CreateQuizStates.choosing_grade)
async def set_create_grade(message: Message, state: FSMContext, translator: Translator, user: User) -> None:
    grade = parse_grade_choice((message.text or "").strip())
    if grade is None:
        await message.answer(translator("manual_choose_grade"), reply_markup=grade_keyboard())
        return

    await state.update_data(grade=grade)
    await state.set_state(None)

    data = await state.get_data()
    await message.answer(
        f"{data.get('subject_name', '')} · {grade}-sinf",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(translator("create_method_prompt"), reply_markup=create_method_keyboard(user.locale))
