import html

from app.database.models import Quiz
from app.i18n import Translator


def format_duration(locale: str, seconds: int) -> str:
    if seconds % 60 == 0:
        minutes = seconds // 60
        if locale == "ru":
            return f"{minutes} мин."
        if locale == "en":
            return f"{minutes} min"
        return f"{minutes} daqiqa"
    if locale == "ru":
        return f"{seconds} сек."
    if locale == "en":
        return f"{seconds} sec"
    return f"{seconds} soniya"


def shuffle_text(translator: Translator, quiz: Quiz) -> str:
    if quiz.shuffle_questions and quiz.shuffle_options:
        return translator("shuffle_all")
    if quiz.shuffle_questions:
        return translator("shuffle_questions_only")
    if quiz.shuffle_options:
        return translator("shuffle_options_only")
    return translator("shuffle_none")


def time_limit_text(translator: Translator, locale: str, quiz: Quiz) -> str:
    if quiz.time_limit_seconds:
        return format_duration(locale, quiz.time_limit_seconds)
    return translator("quiz_created_time_none")


def status_line(translator: Translator, quiz: Quiz) -> str:
    if quiz.attempts_count == 0:
        return translator("quiz_created_no_attempts")
    return translator("quiz_attempts_count", count=quiz.attempts_count)


def summary_line(translator: Translator, locale: str, quiz: Quiz) -> str:
    return translator(
        "quiz_created_summary",
        count=quiz.question_count,
        time=time_limit_text(translator, locale, quiz),
        shuffle=shuffle_text(translator, quiz),
    )


def short_code(quiz: Quiz) -> str:
    return str(quiz.id).replace("-", "")[:8]


def build_quiz_card_text(translator: Translator, locale: str, quiz: Quiz, link: str | None = None, heading: str | None = None) -> str:
    lines = []
    if heading:
        lines.append(heading)
        lines.append("")
    lines.append(f"<b>{html.escape(quiz.title)}</b>")
    if quiz.description:
        lines.append(html.escape(quiz.description))
    if quiz.creator is not None:
        lines.append(translator("quiz_card_creator", creator=html.escape(quiz.creator.display_name)))
    lines.append(f"<i>{status_line(translator, quiz)}</i>")
    lines.append(summary_line(translator, locale, quiz))
    if link:
        lines.append("")
        lines.append(translator("external_sharing_link_label"))
        lines.append(link)
    return "\n".join(lines)


def build_quiz_list_row(translator: Translator, locale: str, index: int, quiz: Quiz) -> str:
    return "\n".join(
        [
            f"{index}. <b>{html.escape(quiz.title)}</b>  <i>{status_line(translator, quiz)}</i>",
            summary_line(translator, locale, quiz),
            f"/view_{short_code(quiz)}",
        ]
    )
