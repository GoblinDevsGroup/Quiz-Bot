import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CreateMethodCB, MenuCB, PdfSettingCB
from app.bot.keyboards.common import cancel_keyboard
from app.bot.keyboards.pdf_generation import (
    difficulty_keyboard,
    generate_confirm_keyboard,
    pdf_language_keyboard,
    question_count_keyboard,
    question_type_keyboard,
)
from app.bot.middlewares.throttling import check_ai_rate_limit
from app.bot.states.pdf_states import PdfQuizStates
from app.core.config import settings
from app.core.security import cleanup_file, is_pdf_signature, safe_temp_path
from app.database.models import User
from app.database.repositories.generation_repository import GenerationRepository
from app.i18n import Translator

router = Router(name="pdf_quiz")


@router.callback_query(CreateMethodCB.filter(F.method == "pdf"))
async def start_pdf_flow(callback: CallbackQuery, state: FSMContext, translator: Translator, user: User) -> None:
    await state.set_state(PdfQuizStates.waiting_for_pdf)
    await callback.message.edit_text(translator("pdf_instructions"), reply_markup=cancel_keyboard(user.locale))
    await callback.answer()


@router.message(PdfQuizStates.waiting_for_pdf, F.document)
async def handle_pdf_upload(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator, redis: ArqRedis
) -> None:
    document = message.document

    if not (document.mime_type in ("application/pdf", "application/x-pdf") or document.file_name.lower().endswith(".pdf")):
        await message.answer(translator("pdf_invalid"))
        return

    if document.file_size and document.file_size > settings.pdf_max_size_bytes:
        await message.answer(translator("pdf_too_large", limit=settings.pdf_max_size_mb))
        return

    if not await check_ai_rate_limit(redis, user.telegram_user_id):
        await message.answer(translator("rate_limited"))
        return

    status_msg = await message.answer(translator("status_downloading"))

    try:
        temp_path = safe_temp_path(settings.pdf_temp_dir, extension=".pdf")
        await message.bot.download(document, destination=temp_path)

        header = temp_path.read_bytes()[:5]
        if not is_pdf_signature(header):
            cleanup_file(temp_path)
            await status_msg.edit_text(translator("pdf_invalid"))
            return

    except Exception:
        await status_msg.edit_text(translator("pdf_invalid"))
        return

    gen_repo = GenerationRepository(session)
    pdf_doc = await gen_repo.create_pdf_document(
        uploader_id=user.id,
        original_filename=document.file_name or "document.pdf",
        stored_filename=temp_path.name,
        file_size_bytes=document.file_size or 0,
        telegram_file_id=document.file_id,
    )

    await state.update_data(
        pdf_document_id=str(pdf_doc.id),
        temp_path=str(temp_path),
        status_message_id=status_msg.message_id,
        question_count=10,
        difficulty="mixed",
        question_type="mixed",
        language="auto",
    )
    await state.set_state(PdfQuizStates.choosing_question_count)
    await status_msg.edit_text(translator("pdf_received"))
    await message.answer(translator("select_question_count"), reply_markup=question_count_keyboard())


@router.message(PdfQuizStates.waiting_for_pdf)
async def handle_pdf_wrong_type(message: Message, translator: Translator) -> None:
    await message.answer(translator("pdf_invalid"))


@router.callback_query(PdfQuizStates.choosing_question_count, PdfSettingCB.filter(F.field == "count"))
async def set_question_count(callback: CallbackQuery, callback_data: PdfSettingCB, state: FSMContext, translator: Translator) -> None:
    await state.update_data(question_count=int(callback_data.value))
    await state.set_state(PdfQuizStates.choosing_difficulty)
    await callback.message.edit_text(translator("select_difficulty"), reply_markup=difficulty_keyboard())
    await callback.answer()


@router.callback_query(PdfQuizStates.choosing_difficulty, PdfSettingCB.filter(F.field == "difficulty"))
async def set_difficulty(callback: CallbackQuery, callback_data: PdfSettingCB, state: FSMContext, translator: Translator) -> None:
    await state.update_data(difficulty=callback_data.value)
    await state.set_state(PdfQuizStates.choosing_question_type)
    await callback.message.edit_text(translator("select_question_type"), reply_markup=question_type_keyboard())
    await callback.answer()


@router.callback_query(PdfQuizStates.choosing_question_type, PdfSettingCB.filter(F.field == "qtype"))
async def set_question_type(callback: CallbackQuery, callback_data: PdfSettingCB, state: FSMContext, translator: Translator) -> None:
    await state.update_data(question_type=callback_data.value)
    await state.set_state(PdfQuizStates.choosing_language)
    await callback.message.edit_text(translator("select_language"), reply_markup=pdf_language_keyboard())
    await callback.answer()


@router.callback_query(PdfQuizStates.choosing_language, PdfSettingCB.filter(F.field == "language"))
async def set_language(callback: CallbackQuery, callback_data: PdfSettingCB, state: FSMContext, translator: Translator, user: User) -> None:
    await state.update_data(language=callback_data.value)
    await state.set_state(PdfQuizStates.generating)
    data = await state.get_data()
    summary = (
        f"📝 {data['question_count']} | 🎯 {data['difficulty']} | 🧩 {data['question_type']} | 🌐 {data['language']}"
    )
    await callback.message.edit_text(summary, reply_markup=generate_confirm_keyboard(user.locale))
    await callback.answer()


@router.callback_query(PdfQuizStates.generating, PdfSettingCB.filter(F.field == "go"))
async def trigger_generation(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    translator: Translator,
    redis: ArqRedis,
) -> None:
    data = await state.get_data()
    gen_repo = GenerationRepository(session)

    generation = await gen_repo.create_generation(
        requester_id=user.id,
        pdf_document_id=uuid.UUID(data["pdf_document_id"]),
        requested_question_count=data["question_count"],
        requested_difficulty=data["difficulty"],
        requested_language=data["language"],
        requested_question_type=data["question_type"],
    )
    await session.commit()

    status_msg = await callback.message.edit_text(translator("status_extracting"))

    await redis.enqueue_job(
        "generate_quiz_from_pdf_task",
        generation_id=str(generation.id),
        pdf_path=data["temp_path"],
        requester_telegram_id=user.telegram_user_id,
        chat_id=callback.message.chat.id,
        status_message_id=status_msg.message_id,
        question_count=data["question_count"],
        difficulty=data["difficulty"],
        question_type=data["question_type"],
        language=data["language"],
        locale=user.locale,
    )

    await state.clear()
    await callback.answer()
