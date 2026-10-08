import json
import re

import pytest

from app.services.ai.base import AIProviderError, AIResponseTruncatedError
from app.services.ai.document_analyzer import SOURCE_BANK, SOURCE_BANK_AI, SOURCE_MATERIAL, plan_document
from app.services.ai.quiz_generator import AIQuizGeneratorService, _parse_quiz_response
from app.services.pdf.analyzer import analyze_document, find_answer_key
from app.services.pdf.chunker import split_into_segments


def _bank_text(n: int, skip: set[int] = frozenset()) -> str:
    return "\n\n".join(
        f"{i}. Savol raqami {i}?\nA) bir\nB) ikki\nC) uch\nD) to'rt" for i in range(1, n + 1) if i not in skip
    )


class SmallBudgetProvider:
    """Answers bank prompts, but 'runs out of tokens' on more than 4 questions."""

    def __init__(self, limit: int = 4):
        self.calls = 0
        self.limit = limit

    async def complete(self, messages, **kwargs):
        self.calls += 1
        numbers = re.findall(r"^(\d+)\. Savol", messages[-1].content, re.MULTILINE)
        if len(numbers) > self.limit:
            raise AIResponseTruncatedError("too long")
        questions = [
            {"question": f"Savol raqami {n}?", "options": ["bir", "ikki", "uch", "to'rt"], "correct_option": 1}
            for n in numbers
        ]
        return json.dumps({"title": "Bank", "questions": questions})


@pytest.mark.asyncio
async def test_truncated_batches_are_split_instead_of_lost():
    analysis = analyze_document(_bank_text(30))
    result = await AIQuizGeneratorService(SmallBudgetProvider()).convert_question_bank(analysis.blocks)
    assert [q.question for q in result.questions] == [f"Savol raqami {i}?" for i in range(1, 31)]


@pytest.mark.asyncio
async def test_ai_extraction_finds_every_question_in_raw_text():
    result = await AIQuizGeneratorService(SmallBudgetProvider(limit=12)).extract_question_bank(_bank_text(40))
    assert len(result.questions) == 40


def test_missing_question_number_does_not_end_the_chain():
    analysis = analyze_document(_bank_text(30, skip={10}))
    assert analysis.question_count == 29
    assert analysis.blocks[-1].startswith("30.")


def test_segments_keep_all_text_and_cut_before_questions():
    text = _bank_text(60)
    segments = split_into_segments(text, 1000)
    assert len(segments) > 1
    assert all(re.match(r"\d+\. Savol", seg) for seg in segments)
    assert sum(len(re.findall(r"^\d+\. Savol", s, re.MULTILINE)) for s in segments) == 60


def test_one_bad_question_does_not_fail_the_whole_response():
    data = {
        "title": "T",
        "questions": [
            {"question": "Good one?", "options": ["a", "b"], "correct_option": 0},
            {"question": "Bad index?", "options": ["a", "b"], "correct_option": 5},
            {"question": "Long explanation?", "options": ["a", "b"], "correct_option": 1, "explanation": "x" * 5000},
        ],
    }
    result = _parse_quiz_response(data)
    assert [q.question for q in result.questions] == ["Good one?", "Long explanation?"]
    assert result.title == "Generated Quiz"


def test_find_answer_key_in_tail():
    text = _bank_text(10) + "\n\nJavoblar:\n" + " ".join(f"{i}-B" for i in range(1, 11))
    assert find_answer_key(text).startswith("Javoblar")
    assert find_answer_key(_bank_text(10)) == ""


WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo"]


class CappedGenerator:
    """Returns at most 10 questions per call, like real models do."""

    def __init__(self):
        self.counter = 0

    async def complete(self, messages, **kwargs):
        asked = int(re.search(r"Generate exactly (\d+)", messages[-1].content).group(1))
        questions = []
        for _ in range(min(asked, 10)):
            self.counter += 1
            n = self.counter
            words = " ".join(WORDS[(n * k * 7) % len(WORDS)] + str(n * k) for k in range(1, 6))
            questions.append({"question": f"{words}?", "options": [f"a{n}", f"b{n}", f"c{n}", f"d{n}"], "correct_option": 0})
        return json.dumps({"title": "Material", "questions": questions})


@pytest.mark.asyncio
async def test_material_generation_reaches_requested_count():
    result = await AIQuizGeneratorService(CappedGenerator()).generate_from_chunks(
        ["Some study text."], question_count=50, difficulty="mixed", question_type="mixed", language="uz"
    )
    assert len(result.questions) == 50


class AnalysisProvider:
    def __init__(self, kind: str, count: int, capacity: int = 0, fail: bool = False):
        self.kind, self.count, self.capacity, self.fail = kind, count, capacity, fail

    async def complete(self, messages, **kwargs):
        if self.fail:
            raise AIProviderError("down")
        questions = [{"label": str(i), "start": f"Savol raqami {i}"} for i in range(1, self.count + 1)]
        return json.dumps({"kind": self.kind, "questions": questions, "material_capacity": self.capacity})


@pytest.mark.asyncio
async def test_plan_uses_regex_split_when_counts_agree():
    plan = await plan_document(AnalysisProvider("test_bank", 30), _bank_text(30))
    assert (plan.source_mode, plan.total) == (SOURCE_BANK, 30)


@pytest.mark.asyncio
async def test_plan_switches_to_ai_extraction_when_regex_undercounts():
    # Numbering breaks after question 9, so the regex only sees 9 questions.
    text = _bank_text(9) + "\n\n" + "\n\n".join(
        f"Savol-{i}: matn?\nA) bir\nB) ikki\nC) uch\nD) to'rt" for i in range(10, 41)
    )
    assert analyze_document(text).question_count == 9
    plan = await plan_document(AnalysisProvider("test_bank", 40), text)
    assert (plan.source_mode, plan.total) == (SOURCE_BANK_AI, 40)


@pytest.mark.asyncio
async def test_plan_material_uses_ai_capacity():
    plan = await plan_document(AnalysisProvider("material", 6, capacity=25), "Study text. " * 300)
    assert (plan.source_mode, plan.total) == (SOURCE_MATERIAL, 25)


@pytest.mark.asyncio
async def test_plan_falls_back_to_regex_when_ai_fails():
    plan = await plan_document(AnalysisProvider("test_bank", 0, fail=True), _bank_text(30))
    assert (plan.source_mode, plan.total) == (SOURCE_BANK, 30)
