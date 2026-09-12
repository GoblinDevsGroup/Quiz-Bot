import json
import math
import re

from pydantic import ValidationError
from rapidfuzz import fuzz

from app.core.logging import get_logger
from app.schemas.ai import AIQuestion, AIQuizResponse
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.prompts import build_generation_messages, build_repair_messages

logger = get_logger(__name__)

DUPLICATE_SIMILARITY_THRESHOLD = 85


class QuizGenerationError(Exception):
    pass


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
        raw = await self.provider.complete(messages)

        try:
            data = _extract_json(raw)
            return AIQuizResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning("ai_response_invalid_attempting_repair", error=str(exc))
            repair_messages = build_repair_messages(raw, str(exc))
            repaired_raw = await self.provider.complete(repair_messages)
            try:
                data = _extract_json(repaired_raw)
                return AIQuizResponse.model_validate(data)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc2:
                logger.error("ai_response_repair_failed", error=str(exc2))
                raise QuizGenerationError("AI returned invalid structured output after repair attempt") from exc2

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
