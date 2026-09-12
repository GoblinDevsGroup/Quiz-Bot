from aiogram import Router

from app.bot.handlers import (
    admin,
    ai_prompt_quiz,
    chat_tracking,
    commands,
    created_quiz,
    edit_quiz,
    group_quiz,
    manual_quiz,
    menu,
    my_quizzes,
    pdf_quiz,
    quiz_bank,
    quiz_preview,
    quiz_taking,
    reply_menu,
    reports,
    schedule_quiz,
    share_inline,
    start,
)


def get_root_router() -> Router:
    root = Router(name="root")
    root.include_router(admin.router)
    root.include_router(chat_tracking.router)
    root.include_router(start.router)
    root.include_router(menu.router)
    # reply_menu and commands (persistent keyboard taps / slash commands) are
    # registered before every FSM-flow router so they always escape a stuck
    # flow instead of being swallowed as free-text input by that flow's state
    # handler (e.g. /stop or /newquiz must work mid-manual-quiz-creation too).
    root.include_router(reply_menu.router)
    root.include_router(commands.router)
    root.include_router(pdf_quiz.router)
    root.include_router(manual_quiz.router)
    root.include_router(edit_quiz.router)
    root.include_router(schedule_quiz.router)
    root.include_router(ai_prompt_quiz.router)
    root.include_router(quiz_bank.router)
    root.include_router(my_quizzes.router)
    root.include_router(quiz_taking.router)
    root.include_router(quiz_preview.router)
    root.include_router(created_quiz.router)
    root.include_router(group_quiz.router)
    root.include_router(share_inline.router)
    root.include_router(reports.router)
    return root
