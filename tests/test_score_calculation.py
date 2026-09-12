from app.database.models import QuizAttempt


def test_score_percent_computation():
    attempt = QuizAttempt()
    attempt.correct_count = 18
    attempt.total_questions = 20
    assert attempt.score_percent == 90.0


def test_score_percent_zero_questions_does_not_divide_by_zero():
    attempt = QuizAttempt()
    attempt.correct_count = 0
    attempt.total_questions = 0
    assert attempt.score_percent == 0.0
