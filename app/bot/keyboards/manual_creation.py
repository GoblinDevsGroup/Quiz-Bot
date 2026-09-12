from typing import Optional

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonPollType,
    ReplyKeyboardMarkup,
)

from app.bot.keyboards.callback_data import CreatedQuizActionCB
from app.i18n import Translator
from app.services.quiz.quiz_presentation import format_duration

# Matches the real @QuizBot's time-limit grid (seconds).
TIME_LIMIT_CHOICES = [
    [10, 15, 30],
    [45, 60, 120],
    [180, 240, 300],
]

SHUFFLE_CHOICES = [
    ["shuffle_all", "shuffle_none"],
    ["shuffle_questions_only", "shuffle_options_only"],
]


def question_collection_keyboard(locale: str, has_questions: bool) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard shown while collecting quiz questions.

    The "create question" button uses Telegram's request_poll button type
    (locked to quiz mode), which makes the client open its native poll
    composer automatically when tapped — the same mechanism the official
    @QuizBot uses. This is the one case a bot CAN open client UI for the
    user; there's no equivalent for opening it any other way.
    """
    _ = Translator(locale)
    rows = [
        [
            KeyboardButton(
                text=_("manual_create_question_button"),
                request_poll=KeyboardButtonPollType(type="quiz"),
            )
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def time_limit_keyboard(locale: str) -> ReplyKeyboardMarkup:
    """Reply keyboard (same persistent bottom-bar style as 'Savol tuzish'),
    replacing it — sending any new ReplyKeyboardMarkup swaps out the old one."""
    rows = [[KeyboardButton(text=format_duration(locale, seconds)) for seconds in row] for row in TIME_LIMIT_CHOICES]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def parse_time_limit_choice(locale: str, text: str) -> Optional[int]:
    for row in TIME_LIMIT_CHOICES:
        for seconds in row:
            if format_duration(locale, seconds) == text:
                return seconds
    return None


def shuffle_keyboard(locale: str) -> ReplyKeyboardMarkup:
    _ = Translator(locale)
    rows = [[KeyboardButton(text=_(key)) for key in row] for row in SHUFFLE_CHOICES]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def parse_shuffle_choice(locale: str, text: str) -> Optional[tuple[bool, bool]]:
    _ = Translator(locale)
    mapping = {
        _("shuffle_all"): (True, True),
        _("shuffle_none"): (False, False),
        _("shuffle_questions_only"): (True, False),
        _("shuffle_options_only"): (False, True),
    }
    return mapping.get(text)


def created_quiz_keyboard(locale: str, quiz_id: str, bot_username: str) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("start_this_quiz_button"), callback_data=CreatedQuizActionCB(action="start", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("start_in_group_button"), url=f"https://t.me/{bot_username}?startgroup=quiz_{quiz_id}")],
            [InlineKeyboardButton(text=_("schedule_in_group_button"), url=f"https://t.me/{bot_username}?startgroup=schedq_{quiz_id}")],
            [InlineKeyboardButton(text=_("share_quiz_button"), switch_inline_query=quiz_id)],
            [InlineKeyboardButton(text=_("edit_quiz_button"), callback_data=CreatedQuizActionCB(action="manage", quiz_id=quiz_id).pack())],
            [InlineKeyboardButton(text=_("quiz_stats_button"), callback_data=CreatedQuizActionCB(action="stats", quiz_id=quiz_id).pack())],
        ]
    )
