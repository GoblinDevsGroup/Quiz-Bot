import pytest
from pydantic import ValidationError

from app.schemas.ai import AIQuestion, AIQuizResponse


def test_valid_question_passes():
    q = AIQuestion(
        question="What is Python?",
        options=["A language", "A snake", "A database", "An OS"],
        correct_option=0,
        explanation="Python is a programming language.",
        difficulty="easy",
    )
    assert q.correct_option == 0


def test_rejects_out_of_range_correct_option():
    with pytest.raises(ValidationError):
        AIQuestion(
            question="What is Python?",
            options=["A", "B"],
            correct_option=5,
            difficulty="easy",
        )


def test_rejects_too_few_options():
    with pytest.raises(ValidationError):
        AIQuestion(question="What is Python?", options=["Only one"], correct_option=0)


def test_filters_empty_option_strings():
    q = AIQuestion(question="What is it?", options=["A", "", "  ", "B"], correct_option=0)
    assert q.options == ["A", "B"]


def test_full_quiz_response_validates():
    response = AIQuizResponse(
        title="Python Basics",
        description="Generated from PDF",
        questions=[
            AIQuestion(question="Q1?", options=["A", "B"], correct_option=1),
        ],
    )
    assert len(response.questions) == 1
