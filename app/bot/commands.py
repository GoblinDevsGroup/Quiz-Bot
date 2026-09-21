"""Bot command menus.

Lives here rather than in main.py so the admin-management handlers can grant
(and revoke) the admin "/" menu the moment an admin is added or removed,
without importing main.py and creating a circular import.
"""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from app.core.logging import get_logger
from app.i18n import t

logger = get_logger(__name__)

ADMIN_COMMANDS = [
    BotCommand(command="admin", description="admin help"),
    BotCommand(command="users", description="list all bot users"),
    BotCommand(command="allquizzes", description="list every quiz (moderation)"),
    BotCommand(command="groups", description="list groups the bot is in"),
    BotCommand(command="broadcast", description="message every bot user"),
    BotCommand(command="ban", description="ban a user by telegram id"),
    BotCommand(command="unban", description="unban a user by telegram id"),
    BotCommand(command="reports", description="list open content reports"),
    BotCommand(command="deletequiz", description="delete a quiz by id"),
    BotCommand(command="finduser", description="find a user by username"),
]


def default_commands(locale: str = "uz") -> list[BotCommand]:
    return [
        BotCommand(command="newquiz", description=t(locale, "cmd_newquiz_desc")),
        BotCommand(command="quizzes", description=t(locale, "cmd_quizzes_desc")),
        BotCommand(command="lang", description=t(locale, "cmd_lang_desc")),
        BotCommand(command="stop", description=t(locale, "cmd_stop_desc")),
    ]


async def grant_admin_commands(bot: Bot, telegram_id: int) -> None:
    """Shows the admin-only commands in this one chat's "/" menu."""
    try:
        await bot.set_my_commands(
            default_commands() + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=telegram_id)
        )
    except Exception as exc:
        logger.warning("admin_command_scope_failed", admin_id=telegram_id, error=str(exc))


async def revoke_admin_commands(bot: Bot, telegram_id: int) -> None:
    """Drops the chat-specific menu so the user falls back to the default one."""
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=telegram_id))
    except Exception as exc:
        logger.warning("admin_command_scope_clear_failed", admin_id=telegram_id, error=str(exc))
