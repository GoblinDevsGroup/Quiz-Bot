import asyncio

from aiogram import Bot

COUNTDOWN_STEPS = ["3...", "2... Tayyormisiz?", "1... Sozlanmoqda...", "🚀 Ketdik!"]
COUNTDOWN_STEP_DELAY_SECONDS = 0.9


async def play_countdown(bot: Bot, chat_id: int) -> None:
    """Shown before the first question, for both solo and group play."""
    message = await bot.send_message(chat_id, COUNTDOWN_STEPS[0])
    for step in COUNTDOWN_STEPS[1:]:
        await asyncio.sleep(COUNTDOWN_STEP_DELAY_SECONDS)
        try:
            await message.edit_text(step)
        except Exception:
            pass
    await asyncio.sleep(COUNTDOWN_STEP_DELAY_SECONDS)
