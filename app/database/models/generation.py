import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import GenerationStatus
from app.database.base import Base, TimestampMixin, UUIDPkMixin


class QuizGeneration(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "quiz_generations"

    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pdf_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pdf_documents.id", ondelete="SET NULL"), nullable=True
    )
    quiz_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default=GenerationStatus.pending.value, nullable=False)
    requested_question_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    requested_difficulty: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)
    requested_language: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    requested_question_type: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)
    ai_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    pdf_document: Mapped[Optional["PdfDocument"]] = relationship(back_populates="generations")
    quiz: Mapped[Optional["Quiz"]] = relationship(back_populates="generation")
