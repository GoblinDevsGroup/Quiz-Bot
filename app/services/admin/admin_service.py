"""Single source of truth for "is this Telegram user an admin?".

Two kinds of admin exist:

* **owners** — the ids in the ADMIN_IDS env var. They can never be removed
  from inside the bot, so the bot can't be locked out of its own admin panel.
* **added admins** — rows in `bot_admins`, added and removed by any admin
  through the panel.

The answer is cached in-process for a few seconds because the admin router's
filter runs against every incoming message; without it each one would cost a
database round-trip. Adding/removing an admin invalidates the cache
immediately, so only the *other* process (the arq worker) can lag, and only
until the TTL expires.
"""

import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.repositories.bot_admin_repository import BotAdminRepository

CACHE_TTL_SECONDS = 15

_cached_db_ids: set[int] = set()
_cached_at: Optional[float] = None


def owner_ids() -> set[int]:
    return set(settings.admin_id_list)


def is_owner(telegram_id: Optional[int]) -> bool:
    return telegram_id is not None and telegram_id in owner_ids()


def invalidate_cache() -> None:
    global _cached_at
    _cached_at = None


async def db_admin_ids(session: AsyncSession) -> set[int]:
    global _cached_db_ids, _cached_at
    now = time.monotonic()
    if _cached_at is not None and now - _cached_at < CACHE_TTL_SECONDS:
        return _cached_db_ids
    _cached_db_ids = set(await BotAdminRepository(session).list_telegram_ids())
    _cached_at = now
    return _cached_db_ids


async def all_admin_ids(session: Optional[AsyncSession]) -> set[int]:
    if session is None:
        return owner_ids()
    return owner_ids() | await db_admin_ids(session)


async def is_admin(session: Optional[AsyncSession], telegram_id: Optional[int]) -> bool:
    if telegram_id is None:
        return False
    if telegram_id in owner_ids():
        return True
    if session is None:
        return False
    return telegram_id in await db_admin_ids(session)
