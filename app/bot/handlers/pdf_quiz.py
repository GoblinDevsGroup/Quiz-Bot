import asyncio
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
from app.core.security import cleanup_file, is_docx_signature, is_pdf_signature, safe_temp_path
from app.services.pdf.validator import DOCX_MIME_TYPE
from app.services.pdf.analyzer import CHARS_PER_MATERIAL_QUESTION, DocumentAnalysis, analyze_document, parse_selection
from app.services.pdf.extractor import PdfExtractionError, extract_text
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

    file_name = (document.file_name or "").lower()
    is_pdf = document.mime_type in ("application/pdf", "application/x-pdf") or file_name.endswith(".pdf")
    is_docx = document.mime_type == DOCX_MIME_TYPE or file_name.endswith(".docx")
    if not (is_pdf or is_docx):
        await message.answer(translator("pdf_invalid"))
        return
    extension = ".pdf" if is_pdf else ".docx"

    if document.file_size and document.file_size > settings.pdf_max_size_bytes:
        await message.answer(translator("pdf_too_large", limit=settings.pdf_max_size_mb))
        return

    if not await check_ai_rate_limit(redis, user.telegram_user_id):
        await message.answer(translator("rate_limited"))
        return

    status_msg = await message.answer(translator("status_downloading"))

    try:
        temp_path = safe_temp_path(settings.pdf_temp_dir, extension=extension)
        await message.bot.download(document, destination=temp_path)

        header = temp_path.read_bytes()[:5]
        signature_ok = is_pdf_signature(header) if is_pdf else is_docx_signature(header)
        if not signature_ok:
            cleanup_file(temp_path)
            await status_msg.edit_text(translator("pdf_invalid"))
            return

    except Exception:
        await status_msg.edit_text(translator("pdf_invalid"))
        return

    # Read the file now so we can tell the user how many questions it holds.
    await status_msg.edit_text(translator("status_extracting"))
    try:
        extraction = await asyncio.to_thread(extract_text, temp_path)
    except PdfExtractionError:
        cleanup_file(temp_path)
        await status_msg.edit_text(translator("pdf_invalid"))
        return
    analysis = analyze_document(extraction.text)

    gen_repo = GenerationRepository(session)
    pdf_doc = await gen_repo.create_pdf_document(
        uploader_id=user.id,
        original_filename=document.file_name or f"document{extension}",
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
        source_mode="bank" if analysis.is_question_bank else "material",
        max_selectable=analysis.max_selectable,
        range_start=None,
        range_end=None,
    )
    await state.set_state(PdfQuizStates.choosing_question_count)
    await status_msg.edit_text(translator("pdf_received"))
    await message.answer(
        _count_prompt(translator, analysis),
        reply_markup=question_count_keyboard(user.locale, analysis.max_selectable),
    )


def _count_prompt(translator: Translator, analysis: DocumentAnalysis) -> str:
    if analysis.is_question_bank:
        return translator("count_prompt_bank", total=analysis.question_count)
    return translator("count_prompt_material", max=analysis.max_selectable)


async def _apply_selection(
    state: FSMContext, translator: Translator, user: User, start: int, end: int, send
) -> None:
    """Store the chosen slice, then either finish (question bank) or continue to the settings."""
    await state.update_data(question_count=end - start + 1, range_start=start, range_end=end)
    data = await state.get_data()

    if data.get("source_mode") == "bank":
        # Questions already exist in the file: difficulty/type/language don't apply.
        await state.set_state(PdfQuizStates.generating)
        summary = translator("count_selected_bank", count=end - start + 1, start=start, end=end)
        await send(summary, generate_confirm_keyboard(user.locale))
        return

    await state.set_state(PdfQuizStates.choosing_difficulty)
    await send(translator("select_difficulty"), difficulty_keyboard())


@router.message(PdfQuizStates.waiting_for_pdf)
async def handle_pdf_wrong_type(message: Message, translator: Translator) -> None:
    await message.answer(translator("pdf_invalid"))


def _analysis_from_state(data: dict) -> DocumentAnalysis:
    """Only the numbers parse_selection needs; the text itself is re-read by the worker."""
    total = data.get("max_selectable", 10)
    if data.get("source_mode") == "bank":
        return DocumentAnalysis(True, blocks=[""] * total)
    return DocumentAnalysis(False, total_chars=total * CHARS_PER_MATERIAL_QUESTION)


@router.callback_query(PdfQuizStates.choosing_question_count, PdfSettingCB.filter(F.field == "count"))
async def set_question_count(
    callback: CallbackQuery, callback_data: PdfSettingCB, state: FSMContext, translator: Translator, user: User
) -> None:
    data = await state.get_data()
    selection = parse_selection(callback_data.value, _analysis_from_state(data))
    if selection is None:
        await callback.answer(translator("count_invalid", total=data.get("max_selectable", 10)), show_alert=True)
        return

    async def send(text, markup):
        await callback.message.edit_text(text, reply_markup=markup)

    await _apply_selection(state, translator, user, *selection, send)
    await callback.answer()


@router.message(PdfQuizStates.choosing_question_count, F.text)
async def set_question_count_from_text(
    message: Message, state: FSMContext, translator: Translator, user: User
) -> None:
    data = await state.get_data()
    selection = parse_selection(message.text, _analysis_from_state(data))
    if selection is None:
        await message.answer(translator("count_invalid", total=data.get("max_selectable", 10)))
        return

    async def send(text, markup):
        await message.answer(text, reply_markup=markup)

    await _apply_selection(state, translator, user, *selection, send)


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
        category_id=data.get("category_id"),
        grade=data.get("grade"),
        source_mode=data.get("source_mode", "material"),
        range_start=data.get("range_start"),
        range_end=data.get("range_end"),
    )

    await state.clear()
    await callback.answer()
