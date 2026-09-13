import uuid
from typing import Optional

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    action: str


class LanguageCB(CallbackData, prefix="lang"):
    code: str


class CreateMethodCB(CallbackData, prefix="create"):
    method: str


class PdfSettingCB(CallbackData, prefix="pdfset"):
    field: str
    value: str


class QuizBankCB(CallbackData, prefix="bank"):
    action: str
    page: int = 1
    quiz_id: Optional[str] = None
    sort: str = "newest"
    category_id: Optional[str] = None
    grade: int = 0


class MyQuizzesCB(CallbackData, prefix="myq"):
    action: str
    status: Optional[str] = None
    page: int = 1
    quiz_id: Optional[str] = None


class QuizActionCB(CallbackData, prefix="qact"):
    action: str
    quiz_id: str


class CategoryCB(CallbackData, prefix="cat"):
    category_id: str


class DifficultyCB(CallbackData, prefix="diff"):
    value: str


class ConfirmCB(CallbackData, prefix="confirm"):
    action: str
    value: str


class PhotoAnswerCB(CallbackData, prefix="pans"):
    attempt_id: str
    option_index: int


class ReportCB(CallbackData, prefix="report"):
    action: str
    quiz_id: Optional[str] = None
    reason: Optional[str] = None


class CreatedQuizActionCB(CallbackData, prefix="qcreated"):
    action: str
    quiz_id: str


class GroupReadyCB(CallbackData, prefix="gready"):
    session_id: str


class GroupStopCB(CallbackData, prefix="gstop"):
    session_id: str


class EditQuizCB(CallbackData, prefix="qedit"):
    action: str
    quiz_id: str
    question_id: Optional[str] = None
    idx: int = 0


class ModerationCB(CallbackData, prefix="mod"):
    action: str
    quiz_id: str


class AdminPanelCB(CallbackData, prefix="adm"):
    action: str
    page: int = 1
