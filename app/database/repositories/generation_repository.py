import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import GenerationStatus
from app.database.models import PdfDocument, QuizGeneration


class GenerationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_pdf_document(
        self,
        uploader_id: uuid.UUID,
        original_filename: str,
        stored_filename: str,
        file_size_bytes: int,
        telegram_file_id: str,
    ) -> PdfDocument:
        doc = PdfDocument(
            uploader_id=uploader_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_size_bytes=file_size_bytes,
            telegram_file_id=telegram_file_id,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def update_pdf_extraction(
        self,
        doc: PdfDocument,
        detected_language: Optional[str],
        page_count: Optional[int],
        used_ocr: bool,
        extracted_char_count: Optional[int],
    ) -> None:
        doc.detected_language = detected_language
        doc.page_count = page_count
        doc.used_ocr = used_ocr
        doc.extracted_char_count = extracted_char_count
        await self.session.flush()

    async def create_generation(
        self,
        requester_id: uuid.UUID,
        pdf_document_id: Optional[uuid.UUID],
        requested_question_count: int,
        requested_difficulty: str,
        requested_language: str,
        requested_question_type: str,
    ) -> QuizGeneration:
        gen = QuizGeneration(
            requester_id=requester_id,
            pdf_document_id=pdf_document_id,
            requested_question_count=requested_question_count,
            requested_difficulty=requested_difficulty,
            requested_language=requested_language,
            requested_question_type=requested_question_type,
        )
        self.session.add(gen)
        await self.session.flush()
        return gen

    async def update_status(
        self,
        generation: QuizGeneration,
        status: GenerationStatus,
        error_message: Optional[str] = None,
    ) -> None:
        generation.status = status.value
        if error_message:
            generation.error_message = error_message
        await self.session.flush()

    async def attach_quiz(self, generation: QuizGeneration, quiz_id: uuid.UUID, ai_model: str) -> None:
        generation.quiz_id = quiz_id
        generation.ai_model = ai_model
        await self.session.flush()

    async def get_by_id(self, generation_id: uuid.UUID) -> Optional[QuizGeneration]:
        return await self.session.get(QuizGeneration, generation_id)
