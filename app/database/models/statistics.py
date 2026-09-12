import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class UserStatistics(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_statistics"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    quizzes_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quizzes_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_questions_answered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_correct_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_incorrect_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_score_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="statistics")

    @property
    def average_score_percent(self) -> float:
        if self.total_questions_answered == 0:
            return 0.0
        return round((self.total_correct_answers / self.total_questions_answered) * 100, 1)

    @property
    def rating(self) -> float:
        # simple 5-star rating derived from average score and completion volume
        base = self.average_score_percent / 20.0
        return round(min(5.0, max(0.0, base)), 1)
