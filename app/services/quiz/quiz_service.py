import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import QuizStatus, QuizVisibility
from app.database.models import Quiz
from app.database.repositories.quiz_repository import QuizRepository
from app.database.repositories.statistics_repository import StatisticsRepository
from app.schemas.ai import AIQuizResponse
from app.schemas.quiz import QuizCreate


class QuizPermissionError(Exception):
    pass


class QuizService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.quiz_repo = QuizRepository(session)
        self.stats_repo = StatisticsRepository(session)

    async def create_manual_quiz(
        self, creator_id: uuid.UUID, data: QuizCreate, status: str = QuizStatus.draft.value
    ) -> Quiz:
        quiz = await self.quiz_repo.create(
            creator_id=creator_id,
            category_id=data.category_id,
            grade=data.grade,
            title=data.title,
            description=data.description,
            difficulty=data.difficulty,
            visibility=data.visibility,
            language=data.language,
            time_limit_seconds=data.time_limit_seconds,
            shuffle_questions=data.shuffle_questions,
            shuffle_options=data.shuffle_options,
            status=status,
            source_type="manual",
        )
        for idx, q in enumerate(data.questions):
            await self.quiz_repo.add_question(
                quiz,
                text=q.text,
                options=q.options,
                correct_option_index=q.correct_option_index,
                explanation=q.explanation,
                difficulty=q.difficulty,
                question_type=q.question_type,
                order_index=idx,
                image_file_id=q.image_file_id,
                source_link=q.source_link,
            )
        await self.stats_repo.on_quiz_created(creator_id)
        # Re-fetch with eager-loaded relationships: the quiz/questions built
        # above only have their FK columns set, not their in-memory
        # relationship collections, so returning `quiz` as-is would make any
        # later access to .questions/.options attempt an implicit async
        # lazy-load (MissingGreenlet). get_by_id() eager-loads everything.
        return await self.quiz_repo.get_by_id(quiz.id)

    async def create_quiz_from_ai(
        self,
        creator_id: uuid.UUID,
        ai_response: AIQuizResponse,
        difficulty_label: str,
        language: str,
        category_id: Optional[uuid.UUID] = None,
    ) -> Quiz:
        quiz = await self.quiz_repo.create(
            creator_id=creator_id,
            category_id=category_id,
            title=ai_response.title,
            description=ai_response.description,
            difficulty=difficulty_label,
            visibility=QuizVisibility.private.value,
            language=language,
            status=QuizStatus.draft.value,
            source_type="pdf_ai",
        )
        for idx, q in enumerate(ai_response.questions):
            await self.quiz_repo.add_question(
                quiz,
                text=q.question,
                options=q.options,
                correct_option_index=q.correct_option,
                explanation=q.explanation,
                difficulty=q.difficulty,
                question_type="multiple_choice" if len(q.options) > 2 else "true_false",
                order_index=idx,
            )
        await self.stats_repo.on_quiz_created(creator_id)
        return await self.quiz_repo.get_by_id(quiz.id)

    async def publish(self, quiz: Quiz, requester_id: uuid.UUID, visibility: str) -> Quiz:
        self._assert_owner(quiz, requester_id)
        if not quiz.questions:
            raise ValueError("Cannot publish a quiz with no questions")
        quiz.status = QuizStatus.published.value
        quiz.visibility = visibility
        await self.session.flush()
        return quiz

    async def submit_for_moderation(self, quiz: Quiz, requester_id: uuid.UUID) -> Quiz:
        self._assert_owner(quiz, requester_id)
        if not quiz.questions:
            raise ValueError("Cannot submit a quiz with no questions")
        quiz.status = QuizStatus.pending.value
        quiz.visibility = QuizVisibility.private.value
        await self.session.flush()
        return quiz

    async def approve_quiz(self, quiz: Quiz, moderator_name: Optional[str] = None) -> Quiz:
        quiz.moderation_number = await self.quiz_repo.next_moderation_number()
        quiz.status = QuizStatus.published.value
        quiz.visibility = QuizVisibility.public.value
        quiz.moderated_by_name = moderator_name
        await self.session.flush()
        return quiz

    async def reject_quiz(self, quiz: Quiz, moderator_name: Optional[str] = None) -> Quiz:
        quiz.status = QuizStatus.draft.value
        quiz.visibility = QuizVisibility.private.value
        quiz.moderated_by_name = moderator_name
        await self.session.flush()
        return quiz

    async def move_question(
        self, quiz: Quiz, requester_id: uuid.UUID, question_id: uuid.UUID, direction: str
    ) -> Quiz:
        self._assert_owner(quiz, requester_id)
        questions = sorted(quiz.questions, key=lambda q: q.order_index)
        idx = next((i for i, q in enumerate(questions) if q.id == question_id), None)
        if idx is None:
            raise ValueError("Question not found")
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(questions):
            questions[idx].order_index, questions[swap_idx].order_index = (
                questions[swap_idx].order_index,
                questions[idx].order_index,
            )
            await self.session.flush()
        return await self.quiz_repo.get_by_id(quiz.id)

    async def archive(self, quiz: Quiz, requester_id: uuid.UUID) -> Quiz:
        self._assert_owner(quiz, requester_id)
        quiz.status = QuizStatus.archived.value
        await self.session.flush()
        return quiz

    async def delete(self, quiz: Quiz, requester_id: uuid.UUID) -> None:
        self._assert_owner(quiz, requester_id)
        await self.quiz_repo.soft_delete(quiz)

    async def update_fields(self, quiz: Quiz, requester_id: uuid.UUID, **fields) -> Quiz:
        self._assert_owner(quiz, requester_id)
        return await self.quiz_repo.update_fields(quiz, **fields)

    async def add_question(
        self,
        quiz: Quiz,
        requester_id: uuid.UUID,
        *,
        text: str,
        options: list[str],
        correct_option_index: int,
        explanation: Optional[str] = None,
        image_file_id: Optional[str] = None,
        source_link: Optional[str] = None,
    ) -> Quiz:
        self._assert_owner(quiz, requester_id)
        await self.quiz_repo.add_question(
            quiz,
            text=text,
            options=options,
            correct_option_index=correct_option_index,
            explanation=explanation,
            order_index=quiz.question_count,
            image_file_id=image_file_id,
            source_link=source_link,
        )
        # Re-fetch: quiz.questions is unloaded for the newly-added row until
        # the relationship is re-hydrated (same reasoning as create_manual_quiz).
        return await self.quiz_repo.get_by_id(quiz.id)

    async def move_question_by_index(self, quiz: Quiz, requester_id: uuid.UUID, position: int, direction: str) -> Quiz:
        self._assert_owner(quiz, requester_id)
        questions = sorted(quiz.questions, key=lambda q: q.order_index)
        if not (0 <= position < len(questions)):
            raise ValueError("Question not found")
        return await self.move_question(quiz, requester_id, questions[position].id, direction)

    async def delete_question_by_index(self, quiz: Quiz, requester_id: uuid.UUID, position: int) -> Quiz:
        self._assert_owner(quiz, requester_id)
        questions = sorted(quiz.questions, key=lambda q: q.order_index)
        if not (0 <= position < len(questions)):
            raise ValueError("Question not found")
        return await self.delete_question(quiz, requester_id, questions[position].id)

    async def delete_question(self, quiz: Quiz, requester_id: uuid.UUID, question_id: uuid.UUID) -> Quiz:
        self._assert_owner(quiz, requester_id)
        question = next((q for q in quiz.questions if q.id == question_id), None)
        if question is None:
            raise ValueError("Question not found")
        if quiz.question_count <= 1:
            raise ValueError("Quiz must keep at least one question")
        await self.quiz_repo.delete_question(question)
        await self.quiz_repo.reindex_questions(quiz.id)
        return await self.quiz_repo.get_by_id(quiz.id, refresh=True)

    def _assert_owner(self, quiz: Quiz, requester_id: uuid.UUID) -> None:
        if quiz.creator_id != requester_id:
            raise QuizPermissionError("User does not own this quiz")

    async def get_public_quiz_or_none(self, quiz_id: uuid.UUID) -> Optional[Quiz]:
        """Used for deep-link access: public quizzes are open to anyone,
        private quizzes are still returned so an owner/direct-link holder
        can view them, but callers must enforce access separately."""
        return await self.quiz_repo.get_by_id(quiz_id)

    def can_view(self, quiz: Quiz, viewer_id: Optional[uuid.UUID]) -> bool:
        if quiz.visibility == QuizVisibility.public.value and quiz.status == QuizStatus.published.value:
            return True
        return viewer_id is not None and quiz.creator_id == viewer_id
