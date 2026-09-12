import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters.admin_filter import IsAdmin
from app.database.repositories.chat_membership_repository import ChatMembershipRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.database.repositories.user_repository import UserRepository
from app.services.quiz.quiz_service import QuizService
from app.services.reports.report_service import ReportService
from app.services.users.user_service import UserService

router = Router(name="admin")
router.message.filter(IsAdmin())

PAGE_SIZE = 15


async def plain(message: Message, text: str) -> None:
    # These are diagnostic/moderation dumps containing raw usernames, quiz
    # titles, and "<placeholder>"-style usage hints — any of which can
    # contain '<'/'>'/'&' that the bot's default HTML parse mode would try
    # (and fail) to interpret as markup. None disables entity parsing for
    # this call only, regardless of the bot-wide default.
    await message.answer(text, parse_mode=None)


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await plain(
        message,
        "Admin commands:\n"
        "/ban [telegram_id]\n"
        "/unban [telegram_id]\n"
        "/reports - list open reports\n"
        "/deletequiz [quiz_id]\n"
        "/finduser [username]\n"
        "/users [page] - list all bot users\n"
        "/allquizzes [page] - list every quiz, any user (moderation)\n"
        "/groups - list groups the bot is currently a member of\n"
        "/broadcast [text] - send a message to every bot user",
    )


@router.message(Command("ban"))
async def ban_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await plain(message, "Usage: /ban [telegram_id]")
        return
    user_service = UserService(session)
    target = await user_service.get_by_telegram_id(int(parts[1]))
    if not target:
        await plain(message, "User not found.")
        return
    await user_service.ban(target)
    await plain(message, f"🚫 Banned {target.display_name}")


@router.message(Command("unban"))
async def unban_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await plain(message, "Usage: /unban [telegram_id]")
        return
    user_service = UserService(session)
    target = await user_service.get_by_telegram_id(int(parts[1]))
    if not target:
        await plain(message, "User not found.")
        return
    await user_service.unban(target)
    await plain(message, f"✅ Unbanned {target.display_name}")


@router.message(Command("reports"))
async def list_reports(message: Message, session: AsyncSession) -> None:
    report_service = ReportService(session)
    reports = await report_service.list_open_reports()
    if not reports:
        await plain(message, "No open reports.")
        return
    lines = [f"#{r.id} quiz={r.quiz_id} reason={r.reason} comment={r.comment or '-'}" for r in reports[:20]]
    await plain(message, "\n".join(lines))


@router.message(Command("deletequiz"))
async def admin_delete_quiz(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    if len(parts) != 2:
        await plain(message, "Usage: /deletequiz [quiz_id]")
        return
    try:
        quiz_id = uuid.UUID(parts[1])
    except ValueError:
        await plain(message, "Invalid quiz id.")
        return

    repo = QuizRepository(session)
    quiz = await repo.get_by_id(quiz_id)
    if not quiz:
        await plain(message, "Quiz not found.")
        return
    await repo.soft_delete(quiz)
    await plain(message, "🗑 Quiz deleted by admin.")


@router.message(Command("finduser"))
async def find_user(message: Message, session: AsyncSession) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await plain(message, "Usage: /finduser [username]")
        return
    user_repo = UserRepository(session)
    users = await user_repo.search_by_username(parts[1])
    if not users:
        await plain(message, "No users found.")
        return
    lines = [f"{u.display_name} | tg_id={u.telegram_user_id} | banned={u.is_banned}" for u in users]
    await plain(message, "\n".join(lines))


@router.message(Command("users"))
async def list_all_users(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1

    user_repo = UserRepository(session)
    quiz_repo = QuizRepository(session)
    users, total = await user_repo.list_all(page=page, page_size=PAGE_SIZE)
    if not users:
        await plain(message, "No users on this page.")
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"👥 Users: {total} total (page {page}/{total_pages})", ""]
    for u in users:
        _quizzes, quiz_count = await quiz_repo.list_by_creator(u.id, page=1, page_size=1)
        ban_flag = " 🚫BANNED" if u.is_banned else ""
        lines.append(f"{u.display_name} | tg_id={u.telegram_user_id} | quizzes={quiz_count}{ban_flag}")
    lines.append("")
    lines.append(f"Next page: /users {page + 1}" if page < total_pages else "(last page)")
    await plain(message, "\n".join(lines))


@router.message(Command("allquizzes"))
async def list_all_quizzes(message: Message, session: AsyncSession) -> None:
    parts = message.text.split()
    page = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 1

    quiz_repo = QuizRepository(session)
    quizzes, total = await quiz_repo.list_all_for_admin(page=page, page_size=PAGE_SIZE)
    if not quizzes:
        await plain(message, "No quizzes on this page.")
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    lines = [f"📚 All quizzes: {total} total (page {page}/{total_pages})", ""]
    for q in quizzes:
        lines.append(
            f"• {q.title} | by {q.creator.display_name} | {q.status}/{q.visibility} | "
            f"{q.question_count}q | id={q.id}"
        )
    lines.append("")
    lines.append("Delete with: /deletequiz [id]")
    lines.append(f"Next page: /allquizzes {page + 1}" if page < total_pages else "(last page)")
    await plain(message, "\n".join(lines))


@router.message(Command("groups"))
async def list_groups(message: Message, session: AsyncSession) -> None:
    repo = ChatMembershipRepository(session)
    groups = await repo.list_active()
    if not groups:
        await plain(message, "Bot is not currently a member of any tracked group.")
        return
    lines = [f"👥 Bot is active in {len(groups)} group(s):", ""]
    for g in groups:
        lines.append(f"• {g.chat_title or '(untitled)'} | {g.chat_type} | chat_id={g.chat_id}")
    await plain(message, "\n".join(lines))


@router.message(Command("broadcast"))
async def broadcast_message(message: Message, redis) -> None:
    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await plain(message, "Usage: /broadcast [message text]")
        return

    await redis.enqueue_job(
        "broadcast_message_task",
        text=text,
        admin_telegram_id=message.from_user.id,
    )
    await plain(message, "📣 Broadcast queued — sending in the background, you'll get a summary when it's done.")
