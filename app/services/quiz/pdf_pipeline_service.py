import uuid
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import GenerationStatus
from app.core.logging import get_logger
from app.core.security import cleanup_file
from app.database.models import PdfDocument, Quiz
from app.database.repositories.generation_repository import GenerationRepository
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.quiz_generator import AIQuizGeneratorService, QuizGenerationError
from app.services.pdf.chunker import detect_language, split_into_chunks
from app.services.pdf.extractor import PdfExtractionError, extract_text
from app.services.quiz.quiz_service import QuizService

logger = get_logger(__name__)

ProgressCallback = Optional[Callable[[GenerationStatus], "None"]]


class PdfPipelineError(Exception):
    pass


class PdfQuizPipelineService:
    """Orchestrates: PDF -> extraction -> chunking -> AI generation -> Quiz persistence."""

    def __init__(self, session: AsyncSession, ai_provider: AIProvider):
        self.session = session
        self.generation_repo = GenerationRepository(session)
        self.quiz_service = QuizService(session)
        self.ai_generator = AIQuizGeneratorService(ai_provider)

    async def run(
        self,
        *,
        generation_id: uuid.UUID,
        pdf_path: Path,
        requester_id: uuid.UUID,
        question_count: int,
        difficulty: str,
        question_type: str,
        language: str,
        category_id: Optional[uuid.UUID] = None,
        on_progress: ProgressCallback = None,
    ) -> Quiz:
        generation = await self.generation_repo.get_by_id(generation_id)
        if generation is None:
            raise PdfPipelineError("Generation record not found")

        try:
            await self._set_status(generation, GenerationStatus.extracting, on_progress)
            extraction = extract_text(pdf_path)

            detected_lang = detect_language(extraction.text)
            effective_language = detected_lang if language == "auto" else language

            # Use the plain FK column (pdf_document_id) rather than the
            # `pdf_document` relationship: this generation object was loaded
            # via session.get() without eager-loading that relationship, so
            # touching it would trigger an implicit async lazy-load, which
            # SQLAlchemy rejects outside an awaited DB call (MissingGreenlet).
            if generation.pdf_document_id:
                pdf_document = await self.session.get(PdfDocument, generation.pdf_document_id)
                if pdf_document is not None:
                    await self.generation_repo.update_pdf_extraction(
                        pdf_document,
                        detected_language=detected_lang,
                        page_count=extraction.page_count,
                        used_ocr=extraction.used_ocr,
                        extracted_char_count=len(extraction.text),
                    )

            await self._set_status(generation, GenerationStatus.analyzing, on_progress)
            chunks = split_into_chunks(extraction.text)

            await self._set_status(generation, GenerationStatus.generating, on_progress)
            ai_result = await self.ai_generator.generate_from_chunks(
                chunks,
                question_count=question_count,
                difficulty=difficulty,
                question_type=question_type,
                language=effective_language or "en",
            )

            await self._set_status(generation, GenerationStatus.validating, on_progress)

            quiz = await self.quiz_service.create_quiz_from_ai(
                creator_id=requester_id,
                ai_response=ai_result,
                difficulty_label=difficulty,
                language=effective_language or "en",
                category_id=category_id,
            )

            await self.generation_repo.attach_quiz(generation, quiz.id, ai_model=self.ai_generator.provider.__class__.__name__)
            await self._set_status(generation, GenerationStatus.completed, on_progress)
            return quiz

        except PdfExtractionError as exc:
            await self._set_status(generation, GenerationStatus.failed, on_progress, error=str(exc))
            raise PdfPipelineError(f"PDF extraction failed: {exc}") from exc
        except (AIProviderError, QuizGenerationError) as exc:
            await self._set_status(generation, GenerationStatus.failed, on_progress, error=str(exc))
            raise PdfPipelineError(f"AI generation failed: {exc}") from exc
        finally:
            cleanup_file(pdf_path)

    async def _set_status(
        self, generation, status: GenerationStatus, on_progress: ProgressCallback, error: Optional[str] = None
    ) -> None:
        await self.generation_repo.update_status(generation, status, error_message=error)
        if on_progress:
            result = on_progress(status)
            if hasattr(result, "__await__"):
                await result
