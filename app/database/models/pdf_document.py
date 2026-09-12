import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class PdfDocument(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "pdf_documents"

    uploader_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_ocr: Mapped[bool] = mapped_column(default=False, nullable=False)
    extracted_char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    generations: Mapped[list["QuizGeneration"]] = relationship(back_populates="pdf_document")
