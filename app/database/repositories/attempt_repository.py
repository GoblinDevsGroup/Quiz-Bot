import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import QuizAttempt, QuizAttemptAnswer


class AttemptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, quiz_id: uuid.UUID, user_id: uuid.UUID, total_questions: int) -> QuizAttempt:
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
            total_questions=total_questions,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def get_by_id(self, attempt_id: uuid.UUID) -> Optional[QuizAttempt]:
        stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id).options(
            selectinload(QuizAttempt.answers)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_answer(
        self,
        attempt: QuizAttempt,
        question_id: uuid.UUID,
        selected_option_index: int,
        is_correct: bool,
    ) -> QuizAttemptAnswer:
        answer = QuizAttemptAnswer(
            attempt_id=attempt.id,
            question_id=question_id,
            selected_option_index=selected_option_index,
            is_correct=is_correct,
            answered_at=datetime.now(timezone.utc),
        )
        self.session.add(answer)
        if is_correct:
            attempt.correct_count += 1
        else:
            attempt.incorrect_count += 1
        attempt.current_question_index += 1
        await self.session.flush()
        return answer

    async def finish(self, attempt: QuizAttempt) -> None:
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.is_completed = True
        attempt.duration_seconds = int((attempt.finished_at - attempt.started_at).total_seconds())
        await self.session.flush()

    async def get_active_for_user(self, user_id: uuid.UUID) -> Optional[QuizAttempt]:
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.is_completed.is_(False))
            .order_by(QuizAttempt.started_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID, limit: int = 20) -> list[QuizAttempt]:
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.is_completed.is_(True))
            .order_by(QuizAttempt.finished_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_quiz(self, quiz_id: uuid.UUID, limit: int = 100) -> list[QuizAttempt]:
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.quiz_id == quiz_id, QuizAttempt.is_completed.is_(True))
            .order_by(QuizAttempt.finished_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
