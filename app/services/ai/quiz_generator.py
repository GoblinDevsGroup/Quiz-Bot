import asyncio
import json
import math
import re

from pydantic import ValidationError
from rapidfuzz import fuzz

from app.core.logging import get_logger
from app.schemas.ai import AIQuestion, AIQuizResponse
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.prompts import (
    build_bank_conversion_messages,
    build_generation_messages,
    build_repair_messages,
)

logger = get_logger(__name__)

DUPLICATE_SIMILARITY_THRESHOLD = 85

BANK_BATCH_SIZE = 15
BANK_BATCH_MAX_CHARS = 7000
BANK_MAX_CONCURRENCY = 4
BANK_MAX_TOKENS = 6000

# Bare URLs embedded in a PDF's extracted text (references, "read more"
# links, etc.). Matched loosely and trimmed of trailing punctuation that's
# almost always sentence punctuation rather than part of the URL.
_URL_RE = re.compile(r"https?://[^\s<>\")]+")


class QuizGenerationError(Exception):
    pass


def _find_source_link(chunk: str) -> str | None:
    match = _URL_RE.search(chunk)
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?)")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(json)?", "", raw).rstrip("`").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in AI response")
    return json.loads(raw[start : end + 1])


def deduplicate_questions(questions: list[AIQuestion]) -> list[AIQuestion]:
    unique: list[AIQuestion] = []
    seen_norms: list[str] = []
    for q in questions:
        norm = _normalize(q.question)
        is_dup = any(fuzz.token_sort_ratio(norm, seen) >= DUPLICATE_SIMILARITY_THRESHOLD for seen in seen_norms)
        if not is_dup:
            unique.append(q)
            seen_norms.append(norm)
    return unique


def _batch_blocks(blocks: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        if current and (len(current) >= BANK_BATCH_SIZE or size + len(block) > BANK_BATCH_MAX_CHARS):
            batches.append(current)
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        batches.append(current)
    return batches


class AIQuizGeneratorService:
    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def _generate_raw(
        self, source_text: str, question_count: int, difficulty: str, question_type: str, language: str
    ) -> AIQuizResponse:
        messages = build_generation_messages(
            source_text=source_text,
            question_count=question_count,
            difficulty=difficulty,
            question_type=question_type,
            language=language,
        )
        return await self._complete_and_parse(messages)

    async def _complete_and_parse(self, messages, *, max_tokens: int | None = None) -> AIQuizResponse:
        extra = {"max_tokens": max_tokens} if max_tokens else {}
        raw = await self.provider.complete(messages, **extra)

        try:
            data = _extract_json(raw)
            return AIQuizResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("ai_response_invalid_attempting_repair", error=str(exc))
            repair_messages = build_repair_messages(raw, str(exc))
            repaired_raw = await self.provider.complete(repair_messages, **extra)
            try:
                data = _extract_json(repaired_raw)
                return AIQuizResponse.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc2:
                logger.error("ai_response_repair_failed", error=str(exc2))
                raise QuizGenerationError("AI returned invalid structured output after repair attempt") from exc2

    async def convert_question_bank(self, blocks: list[str], answer_key: str = "") -> AIQuizResponse:
        """Turn already-written test questions into quiz questions, keeping their order and wording."""
        batches = _batch_blocks(blocks)
        semaphore = asyncio.Semaphore(BANK_MAX_CONCURRENCY)

        async def convert(batch: list[str]) -> AIQuizResponse | None:
            async with semaphore:
                try:
                    return await self._complete_and_parse(
                        build_bank_conversion_messages(question_blocks=batch, answer_key=answer_key),
                        max_tokens=BANK_MAX_TOKENS,
                    )
                except (AIProviderError, QuizGenerationError) as exc:
                    logger.warning("bank_batch_failed", error=str(exc), batch_size=len(batch))
                    return None

        results = await asyncio.gather(*(convert(b) for b in batches))

        questions: list[AIQuestion] = []
        title = ""
        description = ""
        for result in results:
            if result is None:
                continue
            if not title:
                title, description = result.title, result.description
            questions.extend(result.questions)

        if not questions:
            raise QuizGenerationError("AI failed to convert any questions from the document")

        return AIQuizResponse(
            title=title or "Generated Quiz",
            description=description or "Generated from uploaded file",
            questions=questions,
        )

    async def generate_from_chunks(
        self,
        chunks: list[str],
        question_count: int,
        difficulty: str,
        question_type: str,
        language: str,
    ) -> AIQuizResponse:
        if not chunks:
            raise QuizGenerationError("No source text available for generation")

        # Over-generate ~25-30% extra candidates to allow deduplication headroom.
        target_with_buffer = math.ceil(question_count * 1.3)
        per_chunk = max(2, math.ceil(target_with_buffer / len(chunks)))

        all_questions: list[AIQuestion] = []
        title = ""
        description = ""

        for chunk in chunks:
            try:
                result = await self._generate_raw(chunk, per_chunk, difficulty, question_type, language)
            except (AIProviderError, QuizGenerationError) as exc:
                logger.warning("chunk_generation_failed", error=str(exc))
                continue
            if not title:
                title = result.title
                description = result.description

            chunk_link = _find_source_link(chunk)
            if chunk_link:
                for q in result.questions:
                    q.source_link = chunk_link

            all_questions.extend(result.questions)
            if len(deduplicate_questions(all_questions)) >= target_with_buffer:
                break

        if not all_questions:
            raise QuizGenerationError("AI failed to generate any valid questions from the document")

        unique_questions = deduplicate_questions(all_questions)
        final_questions = unique_questions[:question_count]

        if not final_questions:
            raise QuizGenerationError("No valid questions remained after deduplication")

        return AIQuizResponse(
            title=title or "Generated Quiz",
            description=description or "Generated from uploaded PDF",
            questions=final_questions,
        )
