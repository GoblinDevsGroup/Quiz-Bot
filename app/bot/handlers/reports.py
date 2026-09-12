from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.callback_data import ReportCB
from app.bot.states.browse_states import ReportStates
from app.core.enums import ReportReason
from app.database.models import User
from app.i18n import Translator
from app.services.reports.report_service import ReportService

router = Router(name="reports")

REASON_LABELS = {
    ReportReason.spam: "Spam",
    ReportReason.incorrect_content: "Incorrect content",
    ReportReason.inappropriate: "Inappropriate content",
    ReportReason.copyright: "Copyright",
    ReportReason.other: "Other",
}


@router.callback_query(ReportCB.filter(F.action == "start"))
async def start_report(callback: CallbackQuery, callback_data: ReportCB, state: FSMContext) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton(text=label, callback_data=ReportCB(action="reason", quiz_id=callback_data.quiz_id, reason=reason.value).pack())]
        for reason, label in REASON_LABELS.items()
    ]
    await state.set_state(ReportStates.choosing_reason)
    await callback.message.answer("Report reason:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(ReportStates.choosing_reason, ReportCB.filter(F.action == "reason"))
async def choose_reason(callback: CallbackQuery, callback_data: ReportCB, state: FSMContext) -> None:
    await state.update_data(quiz_id=callback_data.quiz_id, reason=callback_data.reason)
    await state.set_state(ReportStates.entering_comment)
    await callback.message.edit_text("Add a comment (or send '-' to skip):")
    await callback.answer()


@router.message(ReportStates.entering_comment)
async def submit_report(message: Message, state: FSMContext, session: AsyncSession, user: User, translator: Translator) -> None:
    import uuid

    data = await state.get_data()
    comment = None if message.text.strip() == "-" else message.text.strip()

    report_service = ReportService(session)
    await report_service.submit_report(uuid.UUID(data["quiz_id"]), user.id, data["reason"], comment)

    await state.clear()
    await message.answer("✅ Thanks, your report has been submitted.")
