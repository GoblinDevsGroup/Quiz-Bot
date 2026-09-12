import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Quiz, QuizAttempt
from app.database.repositories.attempt_repository import AttemptRepository
from app.database.repositories.quiz_repository import QuizRepository
from app.database.repositories.statistics_repository import StatisticsRepository

POINTS_PER_CORRECT_ANSWER = 10


class AttemptService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.attempt_repo = AttemptRepository(session)
        self.quiz_repo = QuizRepository(session)
        self.stats_repo = StatisticsRepository(session)

    async def start_attempt(self, quiz: Quiz, user_id: uuid.UUID) -> QuizAttempt:
        attempt = await self.attempt_repo.create(quiz.id, user_id, quiz.question_count)
        await self.quiz_repo.increment_attempts(quiz)
        return attempt

    async def submit_answer(
        self, attempt: QuizAttempt, question_id: uuid.UUID, selected_index: int, correct_index: int
    ) -> bool:
        is_correct = selected_index == correct_index
        await self.attempt_repo.record_answer(attempt, question_id, selected_index, is_correct)
        return is_correct

    async def finish_attempt(self, attempt: QuizAttempt) -> QuizAttempt:
        await self.attempt_repo.finish(attempt)
        points = attempt.correct_count * POINTS_PER_CORRECT_ANSWER
        await self.stats_repo.on_quiz_completed(
            attempt.user_id,
            correct=attempt.correct_count,
            incorrect=attempt.incorrect_count,
            points=points,
            score_percent=attempt.score_percent,
        )
        return attempt

    async def get_attempt(self, attempt_id: uuid.UUID) -> Optional[QuizAttempt]:
        return await self.attempt_repo.get_by_id(attempt_id)
