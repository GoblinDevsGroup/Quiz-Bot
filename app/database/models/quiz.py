import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Difficulty, QuizSourceType, QuizStatus, QuizVisibility
from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Quiz(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "quizzes"

    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(16), default=Difficulty.mixed.value, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=QuizStatus.draft.value, nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(
        String(16), default=QuizVisibility.private.value, nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(16), default=QuizSourceType.manual.value, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="uz", nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    time_limit_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    moderation_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True, index=True)

    creator: Mapped["User"] = relationship(back_populates="quizzes")
    category: Mapped[Optional["Category"]] = relationship(back_populates="quizzes")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="Question.order_index"
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship(back_populates="quiz", cascade="all, delete-orphan")
    generation: Mapped[Optional["QuizGeneration"]] = relationship(back_populates="quiz", uselist=False)
    reports: Mapped[list["Report"]] = relationship(back_populates="quiz", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_quizzes_visibility_status", "visibility", "status"),
        Index("ix_quizzes_created_at", "created_at"),
    )

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.rating_sum / self.rating_count, 1)


class Question(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(16), default=Difficulty.medium.value, nullable=False)
    question_type: Mapped[str] = mapped_column(String(24), default="multiple_choice", nullable=False)
    correct_option_index: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    options: Mapped[list["AnswerOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="AnswerOption.order_index"
    )


class AnswerOption(UUIDPkMixin, Base):
    __tablename__ = "answer_options"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    question: Mapped["Question"] = relationship(back_populates="options")


class QuizTag(UUIDPkMixin, Base):
    __tablename__ = "quiz_tags"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
