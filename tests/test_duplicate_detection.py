from app.schemas.ai import AIQuestion
from app.services.ai.quiz_generator import deduplicate_questions


def _q(text: str) -> AIQuestion:
    return AIQuestion(question=text, options=["A", "B"], correct_option=0)


def test_exact_duplicates_are_removed():
    questions = [_q("What is a Python list?"), _q("What is a Python list?")]
    result = deduplicate_questions(questions)
    assert len(result) == 1


def test_near_duplicates_are_removed():
    questions = [
        _q("What is a Python list used for?"),
        _q("What is a python list used for"),
    ]
    result = deduplicate_questions(questions)
    assert len(result) == 1


def test_distinct_questions_are_kept():
    questions = [_q("What is a Python list?"), _q("What is a Python dictionary?")]
    result = deduplicate_questions(questions)
    assert len(result) == 2
