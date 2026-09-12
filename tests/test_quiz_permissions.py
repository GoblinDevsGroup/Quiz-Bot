import uuid

from app.core.enums import QuizStatus, QuizVisibility
from app.database.models import Quiz
from app.services.quiz.quiz_service import QuizService


def _make_quiz(status: str, visibility: str, creator_id: uuid.UUID) -> Quiz:
    quiz = Quiz()
    quiz.id = uuid.uuid4()
    quiz.status = status
    quiz.visibility = visibility
    quiz.creator_id = creator_id
    return quiz


def test_public_published_quiz_is_visible_to_anyone():
    service = QuizService(session=None)
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    quiz = _make_quiz(QuizStatus.published.value, QuizVisibility.public.value, owner_id)

    assert service.can_view(quiz, other_id) is True
    assert service.can_view(quiz, None) is True


def test_private_quiz_is_only_visible_to_owner():
    service = QuizService(session=None)
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    quiz = _make_quiz(QuizStatus.draft.value, QuizVisibility.private.value, owner_id)

    assert service.can_view(quiz, owner_id) is True
    assert service.can_view(quiz, other_id) is False
    assert service.can_view(quiz, None) is False


def test_draft_public_quiz_not_visible_until_published():
    service = QuizService(session=None)
    owner_id = uuid.uuid4()
    other_id = uuid.uuid4()
    quiz = _make_quiz(QuizStatus.draft.value, QuizVisibility.public.value, owner_id)

    assert service.can_view(quiz, other_id) is False
    assert service.can_view(quiz, owner_id) is True
