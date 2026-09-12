from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import CreateMethodCB
from app.bot.keyboards.common import cancel_keyboard
from app.bot.keyboards.pdf_generation import preview_keyboard
from app.bot.middlewares.throttling import check_ai_rate_limit
from app.database.models import User
from app.i18n import Translator
from app.services.ai.factory import get_ai_provider
from app.services.ai.quiz_generator import AIQuizGeneratorService, QuizGenerationError
from app.services.quiz.quiz_service import QuizService

router = Router(name="ai_prompt_quiz")


class AIPromptStates(StatesGroup):
    entering_topic = State()


@router.callback_query(CreateMethodCB.filter(F.method == "ai"))
async def start_ai_prompt_flow(callback: CallbackQuery, state: FSMContext, translator: Translator, user: User) -> None:
    await state.set_state(AIPromptStates.entering_topic)
    await callback.message.edit_text(
        "✍️ Mavzuni yozing (masalan: 'Python asoslari', 'Ikkinchi jahon urushi').",
        reply_markup=cancel_keyboard(user.locale),
    )
    await callback.answer()


@router.message(AIPromptStates.entering_topic)
async def generate_from_topic(
    message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator, redis
) -> None:
    topic = message.text.strip()[:500]
    await state.clear()

    if not await check_ai_rate_limit(redis, user.telegram_user_id):
        await message.answer(translator("rate_limited"))
        return

    status_msg = await message.answer(translator("status_generating"))

    try:
        generator = AIQuizGeneratorService(get_ai_provider())
        source = f"Generate a quiz about the following topic using your own reliable knowledge: {topic}"
        result = await generator.generate_from_chunks(
            [source], question_count=10, difficulty="mixed", question_type="mixed", language=user.locale
        )
    except QuizGenerationError:
        await status_msg.edit_text(translator("ai_error_generic"))
        return
    except Exception:
        await status_msg.edit_text(translator("ai_error_generic"))
        return

    quiz_service = QuizService(session)
    quiz = await quiz_service.create_quiz_from_ai(
        creator_id=user.id, ai_response=result, difficulty_label="mixed", language=user.locale
    )

    await status_msg.edit_text(translator("status_completed"))
    text = translator("quiz_preview_title", title=quiz.title) + "\n" + translator(
        "quiz_preview_stats", count=quiz.question_count, difficulty=quiz.difficulty
    )
    await message.answer(text, reply_markup=preview_keyboard(user.locale, str(quiz.id)))
