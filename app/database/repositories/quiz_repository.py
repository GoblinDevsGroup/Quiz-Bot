import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import QuizStatus, QuizVisibility
from app.database.models import AnswerOption, ModerationNotification, Question, Quiz, User


class QuizRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _with_relations(self, stmt):
        return stmt.options(
            selectinload(Quiz.questions).selectinload(Question.options),
            selectinload(Quiz.creator),
            selectinload(Quiz.category),
        )

    async def get_by_id(
        self, quiz_id: uuid.UUID, with_relations: bool = True, refresh: bool = False
    ) -> Optional[Quiz]:
        stmt = select(Quiz).where(Quiz.id == quiz_id, Quiz.is_deleted.is_(False))
        if with_relations:
            stmt = self._with_relations(stmt)
        if refresh:
            # The quiz is already in the identity map; without this its loaded
            # collections (e.g. questions) would stay stale after deletes/reindexing.
            stmt = stmt.execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_moderation(self, quiz_id: uuid.UUID) -> Optional[Quiz]:
        """Load the quiz with a row lock held until the transaction ends, so two
        admins deciding on the same quiz at once are serialized: the second one
        waits, then sees the status the first one set."""
        stmt = (
            self._with_relations(select(Quiz).where(Quiz.id == quiz_id, Quiz.is_deleted.is_(False)))
            .with_for_update(of=Quiz)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_moderation_notification(self, quiz_id: uuid.UUID, admin_telegram_id: int, message_id: int) -> None:
        self.session.add(
            ModerationNotification(quiz_id=quiz_id, admin_telegram_id=admin_telegram_id, message_id=message_id)
        )
        await self.session.flush()

    async def list_moderation_notifications(self, quiz_id: uuid.UUID) -> list[ModerationNotification]:
        stmt = select(ModerationNotification).where(ModerationNotification.quiz_id == quiz_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def clear_moderation_notifications(self, quiz_id: uuid.UUID) -> None:
        await self.session.execute(delete(ModerationNotification).where(ModerationNotification.quiz_id == quiz_id))

    async def create(self, **kwargs) -> Quiz:
        quiz = Quiz(**kwargs)
        self.session.add(quiz)
        await self.session.flush()
        return quiz

    async def add_question(
        self,
        quiz: Quiz,
        text: str,
        options: list[str],
        correct_option_index: int,
        explanation: Optional[str] = None,
        difficulty: str = "medium",
        question_type: str = "multiple_choice",
        order_index: int = 0,
        image_file_id: Optional[str] = None,
        source_link: Optional[str] = None,
    ) -> Question:
        # Note: deliberately never touches quiz.questions / question.options
        # here. Once a Quiz/Question is flushed (persistent), SQLAlchemy's
        # async ORM treats those relationship collections as unloaded and
        # will attempt an implicit lazy-load on any access — including via
        # .append() — which raises MissingGreenlet outside an awaited DB
        # call. Setting the FK columns below is sufficient for persistence;
        # callers that need the relationships populated must re-fetch the
        # quiz through get_by_id(), which eager-loads them.
        question = Question(
            quiz_id=quiz.id,
            text=text,
            explanation=explanation,
            difficulty=difficulty,
            question_type=question_type,
            correct_option_index=correct_option_index,
            order_index=order_index,
            image_file_id=image_file_id,
            source_link=source_link,
        )
        self.session.add(question)
        await self.session.flush()
        for idx, option_text in enumerate(options):
            option = AnswerOption(question_id=question.id, text=option_text, order_index=idx)
            self.session.add(option)
        await self.session.flush()
        return question

    async def list_public(
        self,
        page: int = 1,
        page_size: int = 5,
        category_id: Optional[uuid.UUID] = None,
        grade: Optional[int] = None,
        difficulty: Optional[str] = None,
        search: Optional[str] = None,
        sort: str = "newest",
    ) -> tuple[list[Quiz], int]:
        conditions = [
            Quiz.visibility == QuizVisibility.public.value,
            Quiz.status == QuizStatus.published.value,
            Quiz.is_deleted.is_(False),
        ]
        if category_id:
            conditions.append(Quiz.category_id == category_id)
        if grade:
            conditions.append(Quiz.grade == grade)
        if difficulty:
            conditions.append(Quiz.difficulty == difficulty)
        if search:
            like = f"%{search}%"
            conditions.append(or_(Quiz.title.ilike(like), Quiz.description.ilike(like)))

        count_stmt = select(func.count()).select_from(Quiz).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = self._with_relations(select(Quiz).where(*conditions))
        if sort == "popular":
            stmt = stmt.order_by(Quiz.attempts_count.desc())
        elif sort == "rating":
            stmt = stmt.order_by((Quiz.rating_sum / func.nullif(Quiz.rating_count, 0)).desc().nullslast())
        else:
            stmt = stmt.order_by(Quiz.created_at.desc())

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all()), total

    async def list_by_creator(
        self,
        creator_id: uuid.UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[Quiz], int]:
        conditions = [Quiz.creator_id == creator_id, Quiz.is_deleted.is_(False)]
        if status:
            conditions.append(Quiz.status == status)

        count_stmt = select(func.count()).select_from(Quiz).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = self._with_relations(select(Quiz).where(*conditions)).order_by(Quiz.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all()), total

    async def list_all_for_admin(self, page: int = 1, page_size: int = 20) -> tuple[list[Quiz], int]:
        """Unfiltered by creator/visibility/status — for moderation, where an
        admin needs to find and remove any quiz regardless of who made it."""
        conditions = [Quiz.is_deleted.is_(False)]
        count_stmt = select(func.count()).select_from(Quiz).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = self._with_relations(select(Quiz).where(*conditions)).order_by(Quiz.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all()), total

    async def list_pending_for_admin(self, page: int = 1, page_size: int = 15) -> tuple[list[Quiz], int]:
        """Quizzes submitted by creators and awaiting admin approval."""
        conditions = [Quiz.status == QuizStatus.pending.value, Quiz.is_deleted.is_(False)]
        count_stmt = select(func.count()).select_from(Quiz).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = self._with_relations(select(Quiz).where(*conditions)).order_by(Quiz.created_at.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all()), total

    _MODERATION_NUMBER_LOCK_KEY = 913_004_221

    async def next_moderation_number(self) -> int:
        # Serialize concurrent admin approvals against the shared counter:
        # without this, two approvals reading the same MAX() in parallel
        # would both compute the same next number and one flush would fail
        # the unique constraint. The advisory lock is released automatically
        # at transaction end.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": self._MODERATION_NUMBER_LOCK_KEY})
        stmt = select(func.max(Quiz.moderation_number))
        current = (await self.session.execute(stmt)).scalar_one_or_none() or 0
        return current + 1

    async def soft_delete(self, quiz: Quiz) -> None:
        quiz.is_deleted = True
        await self.session.flush()

    async def update_fields(self, quiz: Quiz, **fields) -> Quiz:
        for key, value in fields.items():
            setattr(quiz, key, value)
        await self.session.flush()
        return quiz

    async def get_question(self, question_id: uuid.UUID) -> Optional[Question]:
        stmt = select(Question).options(selectinload(Question.options)).where(Question.id == question_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_question(self, question: Question) -> None:
        # cascade="all, delete-orphan" on Question.options handles the
        # answer_options rows automatically.
        await self.session.delete(question)
        await self.session.flush()

    async def reindex_questions(self, quiz_id: uuid.UUID) -> None:
        stmt = select(Question).where(Question.quiz_id == quiz_id).order_by(Question.order_index)
        result = await self.session.execute(stmt)
        for idx, question in enumerate(result.scalars().all()):
            question.order_index = idx
        await self.session.flush()

    async def increment_attempts(self, quiz: Quiz) -> None:
        quiz.attempts_count += 1
        await self.session.flush()

    async def add_rating(self, quiz: Quiz, stars: int) -> None:
        quiz.rating_sum += stars
        quiz.rating_count += 1
        await self.session.flush()

    async def top_by_score(self, limit: int = 10) -> Sequence[User]:
        # placeholder for future leaderboard-by-quiz variants
        return []
