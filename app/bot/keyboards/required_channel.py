from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.callback_data import AdminPanelCB, RequiredChannelCB, SubscriptionCB
from app.database.models import RequiredChannel
from app.i18n import Translator


def _channel_url(channel: RequiredChannel) -> str:
    if channel.username:
        return f"https://t.me/{channel.username}"
    return channel.invite_link or f"https://t.me/c/{str(channel.chat_id)[4:]}"


def admin_channels_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    rows = []
    for channel in channels:
        label = channel.title or channel.username or str(channel.chat_id)
        rows.append(
            [
                InlineKeyboardButton(text=f"📢 {label[:40]}", url=_channel_url(channel)),
                InlineKeyboardButton(
                    text="🗑", callback_data=RequiredChannelCB(action="delete", channel_id=channel.id.hex).pack()
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data=RequiredChannelCB(action="add_prompt").pack())])
    rows.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data=AdminPanelCB(action="panel").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_gate_keyboard(locale: str, missing_channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    _ = Translator(locale)
    rows = []
    for channel in missing_channels:
        label = channel.title or channel.username or _("subscribe_channel_fallback_label")
        rows.append([InlineKeyboardButton(text=f"📢 {label}", url=_channel_url(channel))])
    rows.append([InlineKeyboardButton(text=_("subscribe_check_button"), callback_data=SubscriptionCB(action="check").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)
