import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis

from app.core.config import settings
from app.i18n import Translator


class ThrottlingMiddleware(BaseMiddleware):
    """Redis-backed sliding-window rate limiting for general message throughput
    and a separate stricter bucket for AI-triggering actions."""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        key = f"throttle:msg:{tg_user.id}"
        allowed = await self._check_and_increment(key, settings.rate_limit_messages_per_minute, 60)
        if not allowed:
            translator = data.get("translator") or Translator("uz")
            message = getattr(event, "message", None)
            if message:
                await message.answer(translator("rate_limited"))
            return None

        return await handler(event, data)

    async def _check_and_increment(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        _, _, count, _ = await pipe.execute()
        return count <= limit


async def check_ai_rate_limit(redis: Redis, telegram_user_id: int) -> bool:
    key = f"throttle:ai:{telegram_user_id}"
    now = time.time()
    window = 3600
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, count, _ = await pipe.execute()
    return count <= settings.rate_limit_ai_per_hour
