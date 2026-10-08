"""AI-assisted look at an uploaded file: is it a ready-made test bank or study
material, how many test questions does it really contain, and how many
questions could be written from it.

The regex splitter in app/services/pdf/analyzer.py is fast and exact when a
file is numbered cleanly, but a single irregular number (a missing "10.", a
"1-savol" style label, a table) makes it stop early or miss the bank
entirely — users then saw only 6-10 questions offered from files holding
dozens. The AI count is used to catch that and pick the right strategy.
"""

import asyncio
import json
import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.prompts import build_document_analysis_messages
from app.services.pdf.analyzer import (
    CHARS_PER_MATERIAL_QUESTION,
    MATERIAL_MAX_QUESTIONS,
    DocumentAnalysis,
    analyze_document,
)
from app.services.pdf.chunker import split_into_segments

logger = get_logger(__name__)

ANALYSIS_SEGMENT_CHARS = 12000
ANALYSIS_MAX_CONCURRENCY = 4
ANALYSIS_MAX_TOKENS = 16000
ANALYSIS_TIMEOUT_SECONDS = 150
ANALYSIS_MAX_SPLIT_DEPTH = 2
MATERIAL_MIN_QUESTIONS = 5
# Fewer ready-made questions than this is "a few examples", not a test bank.
MIN_BANK_QUESTIONS = 3

SOURCE_BANK = "bank"  # questions split by regex, converted block by block
SOURCE_BANK_AI = "bank_ai"  # AI finds and converts the questions in raw text
SOURCE_MATERIAL = "material"  # new questions generated from study text


@dataclass
class SegmentCount:
    chars: int
    kind: str
    questions: list[tuple[str, str]]
    capacity: int


@dataclass
class DocumentPlan:
    source_mode: str
    # Questions found in the file (bank modes) or the most that may be
    # generated from it (material).
    total: int
    regex: DocumentAnalysis
    ai_question_count: int | None = None


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _parse_segment(raw: str, chars: int) -> SegmentCount:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in analysis response")
    data = json.loads(raw[start : end + 1])
    questions: list[tuple[str, str]] = []
    for item in data.get("questions") or []:
        if isinstance(item, dict):
            questions.append((str(item.get("label") or "").strip(), str(item.get("start") or "").strip()))
        elif isinstance(item, str):
            questions.append(("", item.strip()))
    try:
        capacity = max(0, int(data.get("material_capacity") or 0))
    except (TypeError, ValueError):
        capacity = 0
    kind = "test_bank" if data.get("kind") == "test_bank" else "material"
    return SegmentCount(chars=chars, kind=kind, questions=questions, capacity=capacity)


async def _analyze_segment(provider: AIProvider, segment: str, depth: int = 0) -> list[SegmentCount]:
    try:
        raw = await provider.complete(
            build_document_analysis_messages(segment), temperature=0.0, max_tokens=ANALYSIS_MAX_TOKENS
        )
        return [_parse_segment(raw, len(segment))]
    except (AIProviderError, ValueError) as exc:
        halves = split_into_segments(segment, len(segment) // 2 + 1)
        if len(halves) > 1 and depth < ANALYSIS_MAX_SPLIT_DEPTH:
            results: list[SegmentCount] = []
            for half in halves:
                results.extend(await _analyze_segment(provider, half, depth + 1))
            return results
        raise AIProviderError(f"Document analysis failed: {exc}") from exc


def _merge(segments: list[SegmentCount]) -> tuple[str, int, int]:
    """(kind, question_count, material_capacity) for the whole document."""
    questions: list[tuple[str, str]] = []
    for seg in segments:
        for i, q in enumerate(seg.questions):
            # The same question reported at the end of one piece and the
            # start of the next one (the piece border cut through it).
            if i == 0 and questions and _norm(questions[-1][1]) == _norm(q[1]) and questions[-1][0] == q[0]:
                continue
            questions.append(q)
    bank_chars = sum(s.chars for s in segments if s.kind == "test_bank")
    total_chars = sum(s.chars for s in segments) or 1
    kind = "test_bank" if bank_chars * 2 >= total_chars else "material"
    capacity = sum(s.capacity for s in segments)
    return kind, len(questions), capacity


async def count_with_ai(provider: AIProvider, text: str) -> tuple[str, int, int]:
    segments = split_into_segments(text, ANALYSIS_SEGMENT_CHARS)
    semaphore = asyncio.Semaphore(ANALYSIS_MAX_CONCURRENCY)

    async def run(segment: str) -> list[SegmentCount]:
        async with semaphore:
            return await _analyze_segment(provider, segment)

    results = await asyncio.gather(*(run(s) for s in segments))
    return _merge([seg for part in results for seg in part])


def _material_limit(total_chars: int, ai_capacity: int = 0) -> int:
    estimated = max(ai_capacity, total_chars // CHARS_PER_MATERIAL_QUESTION)
    return max(MATERIAL_MIN_QUESTIONS, min(MATERIAL_MAX_QUESTIONS, estimated))


async def plan_document(provider: AIProvider, text: str) -> DocumentPlan:
    regex = analyze_document(text)
    try:
        kind, ai_count, capacity = await asyncio.wait_for(
            count_with_ai(provider, text), timeout=ANALYSIS_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001
        # The AI count is a cross-check; without it fall back to the regex result.
        logger.warning("ai_document_analysis_failed", error=str(exc))
        if regex.is_question_bank:
            return DocumentPlan(SOURCE_BANK, regex.question_count, regex)
        return DocumentPlan(SOURCE_MATERIAL, _material_limit(len(text)), regex)

    logger.info(
        "document_analyzed",
        ai_kind=kind,
        ai_questions=ai_count,
        ai_capacity=capacity,
        regex_bank=regex.is_question_bank,
        regex_questions=regex.question_count,
    )

    is_bank = (kind == "test_bank" and ai_count >= MIN_BANK_QUESTIONS) or (
        # The AI called it material but the clean regex split agrees there
        # are many ready-made questions: a test bank with a long preface.
        regex.is_question_bank and regex.question_count >= 20 and ai_count >= regex.question_count * 0.8
    )
    if not is_bank:
        return DocumentPlan(SOURCE_MATERIAL, _material_limit(len(text), capacity), regex, ai_count)

    # The regex split keeps the exact wording and document answer keys, so
    # use it whenever it found (about) as many questions as the AI did.
    tolerance = max(1, ai_count // 50)
    if regex.is_question_bank and regex.question_count >= ai_count - tolerance:
        return DocumentPlan(SOURCE_BANK, regex.question_count, regex, ai_count)
    return DocumentPlan(SOURCE_BANK_AI, max(ai_count, regex.question_count), regex, ai_count)
