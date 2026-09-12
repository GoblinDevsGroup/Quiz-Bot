from aiogram import Router
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.chat_membership_repository import ChatMembershipRepository

router = Router(name="chat_tracking")

INACTIVE_STATUSES = {"left", "kicked"}


@router.my_chat_member()
async def track_bot_membership(event: ChatMemberUpdated, session: AsyncSession) -> None:
    # Telegram has no "list the chats I'm in" endpoint, so this is the only
    # way to know which groups the bot currently belongs to — it's rebuilt
    # entirely from these membership-change notifications.
    if event.chat.type not in ("group", "supergroup"):
        return

    status = event.new_chat_member.status
    is_active = status not in INACTIVE_STATUSES

    repo = ChatMembershipRepository(session)
    await repo.upsert(
        chat_id=event.chat.id,
        chat_title=event.chat.title,
        chat_type=event.chat.type,
        member_count=None,
        is_active=is_active,
    )
