import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeChat
from arq import create_pool
from arq.connections import RedisSettings

from app.bot.handlers import get_root_router
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.error_handler import ErrorHandlingMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user_context import UserContextMiddleware
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.database.repositories.category_repository import CategoryRepository
from app.database.session import async_session_factory
from app.i18n import SUPPORTED_LOCALES, t

logger = get_logger(__name__)


class RedisInjectorMiddleware:
    def __init__(self, redis_pool):
        self.redis_pool = redis_pool

    async def __call__(self, handler, event, data):
        data["redis"] = self.redis_pool
        return await handler(event, data)


async def bootstrap_defaults() -> None:
    async with async_session_factory() as session:
        category_repo = CategoryRepository(session)
        await category_repo.ensure_defaults()
        await category_repo.ensure_canonical_subjects()
        await session.commit()


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


async def register_bot_commands(bot: Bot) -> None:
    for locale in SUPPORTED_LOCALES:
        commands = [
            BotCommand(command="newquiz", description=t(locale, "cmd_newquiz_desc")),
            BotCommand(command="quizzes", description=t(locale, "cmd_quizzes_desc")),
            BotCommand(command="lang", description=t(locale, "cmd_lang_desc")),
            BotCommand(command="stop", description=t(locale, "cmd_stop_desc")),
        ]
        await bot.set_my_commands(commands, language_code=locale)

    # setMyCommands can be scoped to a specific chat (BotCommandScopeChat),
    # which is how admin-only commands show up in the "/" menu only for
    # admins — everyone else keeps the plain list set above.
    default_commands = [
        BotCommand(command="newquiz", description=t("uz", "cmd_newquiz_desc")),
        BotCommand(command="quizzes", description=t("uz", "cmd_quizzes_desc")),
        BotCommand(command="lang", description=t("uz", "cmd_lang_desc")),
        BotCommand(command="stop", description=t("uz", "cmd_stop_desc")),
    ]
    for admin_id in settings.admin_id_list:
        try:
            await bot.set_my_commands(default_commands + ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as exc:
            logger.warning("admin_command_scope_failed", admin_id=admin_id, error=str(exc))


async def main() -> None:
    configure_logging()
    logger.info("bot_starting", environment=settings.environment)

    await bootstrap_defaults()

    # No default parse_mode: most messages embed raw user content (quiz
    # titles, usernames, comments) that would break HTML entity parsing if
    # it contains '<'/'>'/'&'. The few messages that deliberately use <b>/<i>
    # markup (and escape their inputs) pass parse_mode="HTML" explicitly.
    # Quiz titles/descriptions/creator-provided links regularly contain raw
    # URLs; disabling link previews bot-wide keeps quiz cards compact instead
    # of a big preview card pushing the actual quiz info off-screen.
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=None, link_preview_is_disabled=True))
    await register_bot_commands(bot)
    storage = RedisStorage.from_url(settings.redis_fsm_url)
    dp = Dispatcher(storage=storage)

    arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    dp.update.outer_middleware(ErrorHandlingMiddleware())
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())
    dp.update.outer_middleware(RedisInjectorMiddleware(arq_redis))
    dp.message.middleware(ThrottlingMiddleware(arq_redis))

    dp.include_router(get_root_router())

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await arq_redis.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
