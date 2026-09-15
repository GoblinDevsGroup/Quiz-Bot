from aiogram import Bot

from app.core.logging import get_logger
from app.database.models import RequiredChannel

logger = get_logger(__name__)

NOT_SUBSCRIBED_STATUSES = {"left", "kicked"}


async def get_missing_channels(bot: Bot, channels: list[RequiredChannel], telegram_user_id: int) -> list[RequiredChannel]:
    """Returns the subset of `channels` the given user is not currently a
    member of. A channel this fails to check (bot lost its admin rights,
    channel was deleted, etc.) is treated as satisfied rather than blocking
    real users over an admin-side misconfiguration — it's logged instead."""
    missing = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel.chat_id, telegram_user_id)
        except Exception as exc:
            logger.warning("subscription_check_failed", chat_id=channel.chat_id, error=str(exc))
            continue
        if member.status in NOT_SUBSCRIBED_STATUSES:
            missing.append(channel)
    return missing
