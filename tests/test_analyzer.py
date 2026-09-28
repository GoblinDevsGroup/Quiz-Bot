import json

import pytest

from app.services.ai.quiz_generator import AIQuizGeneratorService, _batch_blocks
from app.services.pdf.analyzer import analyze_document, parse_selection


def _bank_text(n: int, with_key: bool = False) -> str:
    parts = []
    for i in range(1, n + 1):
        parts.append(f"{i}. Savol raqami {i}?\nA) bir\nB) ikki\nC) uch\nD) to'rt")
    text = "\n\n".join(parts)
    if with_key:
        text += "\n\nJavoblar:\n" + " ".join(f"{i}-B" for i in range(1, n + 1))
    return text


def test_detects_question_bank_and_counts():
    analysis = analyze_document(_bank_text(200))
    assert analysis.is_question_bank
    assert analysis.question_count == 200
    assert analysis.max_selectable == 200
    assert analysis.blocks[0].startswith("1. Savol raqami 1?")
    assert analysis.blocks[199].startswith("200. Savol raqami 200?")


def test_answer_key_is_split_from_last_question():
    analysis = analyze_document(_bank_text(10, with_key=True))
    assert analysis.question_count == 10
    assert "Javoblar" not in analysis.blocks[-1]
    assert analysis.answer_key.startswith("Javoblar")
    assert "10-B" in analysis.answer_key


def test_plain_text_is_material_not_bank():
    text = "Photosynthesis is a process used by plants. " * 200
    analysis = analyze_document(text)
    assert not analysis.is_question_bank
    assert 5 <= analysis.max_selectable <= 100


def test_numbered_list_without_options_is_not_bank():
    text = "\n".join(f"{i}. Just a numbered fact number {i}." for i in range(1, 20))
    assert not analyze_document(text).is_question_bank


def test_parse_selection_bank():
    analysis = analyze_document(_bank_text(200))
    assert parse_selection("30", analysis) == (1, 30)
    assert parse_selection("1-50", analysis) == (1, 50)
    assert parse_selection("51 – 120", analysis) == (51, 120)
    assert parse_selection("hammasi", analysis) == (1, 200)
    assert parse_selection("Все", analysis) == (1, 200)
    assert parse_selection("all", analysis) == (1, 200)


@pytest.mark.parametrize("bad", ["0", "201", "50-10", "0-5", "1-201", "abc", "", "-5"])
def test_parse_selection_rejects_invalid(bad):
    assert parse_selection(bad, analyze_document(_bank_text(200))) is None


def test_parse_selection_material_rejects_ranges_and_overflow():
    analysis = analyze_document("Plain study text. " * 500)
    limit = analysis.max_selectable
    assert parse_selection("5", analysis) == (1, 5)
    assert parse_selection("all", analysis) == (1, limit)
    assert parse_selection("2-5", analysis) is None
    assert parse_selection(str(limit + 1), analysis) is None


def test_batches_respect_size_limits():
    batches = _batch_blocks([f"q{i}" for i in range(40)])
    assert [len(b) for b in batches] == [15, 15, 10]
    big = _batch_blocks(["x" * 4000, "y" * 4000, "z" * 100])
    assert [len(b) for b in big] == [1, 2]


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        prompt = messages[-1].content
        numbers = [int(line.split(".")[0]) for line in prompt.splitlines() if line[:1].isdigit() and ". Savol" in line]
        questions = [
            {"question": f"Savol raqami {n}?", "options": ["bir", "ikki", "uch", "to'rt"], "correct_option": 1}
            for n in numbers
        ]
        return json.dumps({"title": "Test bank", "description": "d", "questions": questions})


@pytest.mark.asyncio
async def test_convert_question_bank_keeps_all_questions_in_order():
    analysis = analyze_document(_bank_text(40))
    provider = FakeProvider()
    result = await AIQuizGeneratorService(provider).convert_question_bank(analysis.blocks[9:35])
    assert provider.calls == 2  # 26 questions -> 15 + 11
    assert len(result.questions) == 26
    assert result.questions[0].question == "Savol raqami 10?"
    assert result.questions[-1].question == "Savol raqami 35?"
