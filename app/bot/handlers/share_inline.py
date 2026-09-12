import uuid

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.quiz_repository import QuizRepository
from app.i18n import SUPPORTED_LOCALES, Translator
from app.services.quiz.quiz_presentation import build_quiz_card_text

router = Router(name="share_inline")


@router.inline_query()
async def handle_share_inline_query(inline_query: InlineQuery, session: AsyncSession) -> None:
    # Powers every "share" button (switch_inline_query=<quiz_id>): tapping one
    # opens Telegram's own universal chat picker, and whatever chat the user
    # picks receives this article — a single, self-contained action with no
    # follow-up messages needed, so it works regardless of bot membership.
    quiz_id_raw = inline_query.query.strip()
    quiz_repo = QuizRepository(session)
    quiz = None
    try:
        quiz = await quiz_repo.get_by_id(uuid.UUID(quiz_id_raw))
    except ValueError:
        pass

    if quiz is None:
        await inline_query.answer([], cache_time=1, is_personal=True)
        return

    lang = inline_query.from_user.language_code
    locale = lang if lang in SUPPORTED_LOCALES else "uz"
    translator = Translator(locale)

    bot_info = await inline_query.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=quiz_{quiz.id}"
    text = build_quiz_card_text(translator, locale, quiz, link=None)

    result = InlineQueryResultArticle(
        id=str(quiz.id),
        title=translator("group_inline_title", title=quiz.title),
        description=translator("group_inline_description", count=quiz.question_count),
        input_message_content=InputTextMessageContent(message_text=text, parse_mode="HTML"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=translator("start_this_quiz_button"), url=link)],
                [
                    InlineKeyboardButton(
                        text=translator("start_in_group_button"),
                        url=f"https://t.me/{bot_info.username}?startgroup=quiz_{quiz.id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=translator("schedule_in_group_button"),
                        url=f"https://t.me/{bot_info.username}?startgroup=schedq_{quiz.id}",
                    )
                ],
                [InlineKeyboardButton(text=translator("share_quiz_button"), switch_inline_query=str(quiz.id))],
            ]
        ),
    )
    await inline_query.answer([result], cache_time=1, is_personal=True)
