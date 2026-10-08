import asyncio
import json
import math
import random
import re

from pydantic import ValidationError
from rapidfuzz import fuzz

from app.core.logging import get_logger
from app.schemas.ai import AIQuestion, AIQuizResponse
from app.services.ai.base import AIProvider, AIProviderError
from app.services.ai.prompts import (
    build_bank_conversion_messages,
    build_bank_extraction_messages,
    build_generation_messages,
    build_repair_messages,
    build_topic_messages,
)
from app.services.pdf.chunker import split_into_segments

logger = get_logger(__name__)

DUPLICATE_SIMILARITY_THRESHOLD = 85

# Kept small on purpose: reasoning models spend part of max_tokens on hidden
# thinking, and 15-question batches regularly came back empty, silently
# losing most of a file's questions. A failed batch is also split in half
# and retried (see _convert_batch), so nothing is dropped for being too big.
BANK_BATCH_SIZE = 8
BANK_BATCH_MAX_CHARS = 4500
BANK_MAX_CONCURRENCY = 4
BANK_MAX_TOKENS = 32000
BANK_MAX_SPLIT_DEPTH = 3
# Raw-text extraction (used when the numbering in the file is too irregular
# for the regex splitter): size of each piece of text sent to the AI.
EXTRACTION_SEGMENT_CHARS = 4000
# How many questions on each side of a segment border are checked for the
# same question having been extracted twice.
EXTRACTION_BORDER_OVERLAP = 3

# Models reliably return only ~10-15 questions per call however many are
# asked for, so bigger requests are split into several calls and topped up
# in extra rounds until the requested count is reached.
MAX_QUESTIONS_PER_CALL = 12
GENERATION_MAX_ROUNDS = 3
GENERATION_MAX_CONCURRENCY = 4
GENERATION_MAX_TOKENS = 24000
MAX_AVOID_QUESTIONS = 80

# Generation is mostly about factual accuracy, not creativity; a low
# temperature noticeably cuts down on wrong answer keys. Converting an
# existing question bank should be as deterministic as possible.
GENERATION_TEMPERATURE = 0.3
BANK_TEMPERATURE = 0.1

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


def _parse_quiz_response(data: dict) -> AIQuizResponse:
    """Validate question by question, so one malformed item (bad index, a
    single option, an over-long explanation) drops only itself instead of
    failing - and losing - the whole batch."""
    if not isinstance(data, dict):
        raise ValueError("AI response is not a JSON object")
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("AI response has no 'questions' list")

    questions: list[AIQuestion] = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if isinstance(item.get("explanation"), str):
            item["explanation"] = item["explanation"][:1000]
        try:
            questions.append(AIQuestion.model_validate(item))
        except ValidationError:
            continue

    dropped = len(raw_questions) - len(questions)
    if dropped:
        logger.warning("ai_questions_dropped_invalid", dropped=dropped, kept=len(questions))
    if raw_questions and not questions:
        raise ValueError("None of the AI questions passed validation")

    title = str(data.get("title") or "").strip()[:255]
    return AIQuizResponse.model_construct(
        title=title if len(title) >= 3 else "Generated Quiz",
        description=str(data.get("description") or "").strip()[:1000],
        questions=questions,
    )


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


def _has_distinct_options(q: AIQuestion) -> bool:
    return len({_normalize(o) for o in q.options}) == len(q.options)


def shuffle_options(q: AIQuestion) -> AIQuestion:
    """Models put the correct answer in the first or second slot far more
    often than chance, which players quickly learn to exploit. True/false
    questions keep their natural order."""
    if len(q.options) <= 2:
        return q
    correct_text = q.options[q.correct_option]
    options = q.options[:]
    random.shuffle(options)
    return q.model_copy(update={"options": options, "correct_option": options.index(correct_text)})


def _usable(questions: list[AIQuestion]) -> list[AIQuestion]:
    return [q for q in deduplicate_questions(questions) if _has_distinct_options(q)]


def _clean_generated(questions: list[AIQuestion]) -> list[AIQuestion]:
    return [shuffle_options(q) for q in _usable(questions)]


def _merge_extracted_segments(parts: list[list[AIQuestion]]) -> list[AIQuestion]:
    """Join per-segment results, dropping a question only when it is the
    exact same stem and options as one just before the segment border (the
    AI saw it at the end of one piece and the start of the next). Fuzzy
    dedup is wrong here: real banks hold questions like "2+3=?" / "2+4=?"."""
    def key(q: AIQuestion) -> str:
        return _normalize(q.question + " | " + " | ".join(q.options))

    merged: list[AIQuestion] = []
    for part in parts:
        recent = {key(q) for q in merged[-EXTRACTION_BORDER_OVERLAP:]}
        for i, q in enumerate(part):
            if i < EXTRACTION_BORDER_OVERLAP and key(q) in recent:
                continue
            merged.append(q)
    return merged


def _apply_known_answers(questions: list[AIQuestion], answers: list[int | None]) -> None:
    # Only safe when the model returned exactly one question per block (it may
    # skip malformed ones); otherwise positions no longer line up.
    if len(questions) != len(answers):
        return
    overridden = 0
    for q, answer in zip(questions, answers):
        if answer is not None and answer < len(q.options) and answer != q.correct_option:
            q.correct_option = answer
            q.explanation = ""  # it argued for the model's (wrong) pick
            overridden += 1
    if overridden:
        logger.info("bank_answers_overridden_from_document", count=overridden)


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


def _plan_generation_jobs(
    chunk_count: int, wanted: int, offset: int
) -> list[tuple[int, int, tuple[int, int] | None]]:
    """Spread `wanted` questions over the chunks as (chunk_index, count, focus)
    jobs of at most MAX_QUESTIONS_PER_CALL each. Several jobs on the same
    chunk each get a different part of it to focus on."""
    base, extra = divmod(wanted, chunk_count)
    jobs: list[tuple[int, int, tuple[int, int] | None]] = []
    for i in range(chunk_count):
        idx = (i + offset) % chunk_count
        count = base + (1 if i < extra else 0)
        if count <= 0:
            continue
        parts = math.ceil(count / MAX_QUESTIONS_PER_CALL)
        per_part, rest = divmod(count, parts)
        for part in range(parts):
            n = per_part + (1 if part < rest else 0)
            jobs.append((idx, n, (part + 1, parts) if parts > 1 else None))
    return jobs


class AIQuizGeneratorService:
    def __init__(self, provider: AIProvider):
        self.provider = provider
        # Title/description of the first bank batch that succeeded.
        self._title = ""
        self._description = ""

    def _remember_title(self, result: AIQuizResponse) -> None:
        if not self._title and result.title != "Generated Quiz":
            self._title, self._description = result.title, result.description

    async def _generate_raw(
        self,
        source_text: str,
        question_count: int,
        difficulty: str,
        question_type: str,
        language: str,
        avoid_questions: list[str] | None = None,
        focus: tuple[int, int] | None = None,
    ) -> AIQuizResponse:
        messages = build_generation_messages(
            source_text=source_text,
            question_count=question_count,
            difficulty=difficulty,
            question_type=question_type,
            language=language,
            avoid_questions=avoid_questions,
            focus=focus,
        )
        return await self._complete_and_parse(
            messages, max_tokens=GENERATION_MAX_TOKENS, temperature=GENERATION_TEMPERATURE
        )

    async def _complete_and_parse(
        self, messages, *, max_tokens: int | None = None, temperature: float = GENERATION_TEMPERATURE
    ) -> AIQuizResponse:
        extra = {"max_tokens": max_tokens} if max_tokens else {}
        raw = await self.provider.complete(messages, temperature=temperature, **extra)

        try:
            return _parse_quiz_response(_extract_json(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("ai_response_invalid_attempting_repair", error=str(exc))
            repair_messages = build_repair_messages(raw, str(exc))
            repaired_raw = await self.provider.complete(repair_messages, temperature=0.0, **extra)
            try:
                return _parse_quiz_response(_extract_json(repaired_raw))
            except (json.JSONDecodeError, ValueError) as exc2:
                logger.error("ai_response_repair_failed", error=str(exc2))
                raise QuizGenerationError("AI returned invalid structured output after repair attempt") from exc2

    async def _convert_batch(
        self, batch: list[str], batch_answers: list[int | None], answer_key: str, depth: int = 0
    ) -> list[AIQuestion]:
        """Convert one batch; if the model fails on it (most often by running
        out of tokens), split it in half and try each half on its own."""
        try:
            result = await self._complete_and_parse(
                build_bank_conversion_messages(question_blocks=batch, answer_key=answer_key),
                max_tokens=BANK_MAX_TOKENS,
                temperature=BANK_TEMPERATURE,
            )
        except (AIProviderError, QuizGenerationError) as exc:
            if len(batch) > 1 and depth < BANK_MAX_SPLIT_DEPTH:
                logger.info("bank_batch_split_retry", error=str(exc), batch_size=len(batch))
                mid = len(batch) // 2
                first = await self._convert_batch(batch[:mid], batch_answers[:mid], answer_key, depth + 1)
                second = await self._convert_batch(batch[mid:], batch_answers[mid:], answer_key, depth + 1)
                return first + second
            logger.warning("bank_batch_failed", error=str(exc), batch_size=len(batch))
            return []
        _apply_known_answers(result.questions, batch_answers)
        self._remember_title(result)
        return result.questions

    async def convert_question_bank(
        self, blocks: list[str], answer_key: str = "", known_answers: list[int | None] | None = None
    ) -> AIQuizResponse:
        """Turn already-written test questions into quiz questions, keeping their order and wording.

        `known_answers` (one per block, parsed from the document itself)
        override the model's choice wherever the document states the answer."""
        batches = _batch_blocks(blocks)
        answers = known_answers or [None] * len(blocks)
        answer_batches: list[list[int | None]] = []
        offset = 0
        for batch in batches:
            answer_batches.append(answers[offset : offset + len(batch)])
            offset += len(batch)
        semaphore = asyncio.Semaphore(BANK_MAX_CONCURRENCY)

        async def convert(batch: list[str], batch_answers: list[int | None]) -> list[AIQuestion]:
            async with semaphore:
                return await self._convert_batch(batch, batch_answers, answer_key)

        results = await asyncio.gather(*(convert(b, a) for b, a in zip(batches, answer_batches)))
        questions = [q for batch_questions in results for q in batch_questions]

        if not questions:
            raise QuizGenerationError("AI failed to convert any questions from the document")
        if len(questions) < len(blocks):
            logger.warning("bank_questions_missing", expected=len(blocks), got=len(questions))

        return AIQuizResponse(
            title=self._title or "Generated Quiz",
            description=self._description or "Generated from uploaded file",
            questions=questions,
        )

    async def _extract_segment(self, segment: str, answer_key: str, depth: int = 0) -> list[AIQuestion]:
        try:
            result = await self._complete_and_parse(
                build_bank_extraction_messages(text=segment, answer_key=answer_key),
                max_tokens=BANK_MAX_TOKENS,
                temperature=BANK_TEMPERATURE,
            )
            self._remember_title(result)
            return result.questions
        except (AIProviderError, QuizGenerationError) as exc:
            halves = split_into_segments(segment, len(segment) // 2 + 1)
            if len(halves) > 1 and depth < BANK_MAX_SPLIT_DEPTH:
                logger.info("extraction_segment_split_retry", error=str(exc), chars=len(segment))
                questions: list[AIQuestion] = []
                for half in halves:
                    questions.extend(await self._extract_segment(half, answer_key, depth + 1))
                return questions
            logger.warning("extraction_segment_failed", error=str(exc), chars=len(segment))
            return []

    async def extract_question_bank(self, text: str, answer_key: str = "") -> AIQuizResponse:
        """Let the AI itself find and convert every test question in raw text.

        Used when the file's numbering/layout is too irregular for the regex
        splitter in analyzer.py, which then finds only part of the questions."""
        segments = split_into_segments(text, EXTRACTION_SEGMENT_CHARS)
        semaphore = asyncio.Semaphore(BANK_MAX_CONCURRENCY)

        async def extract(segment: str) -> list[AIQuestion]:
            async with semaphore:
                return await self._extract_segment(segment, answer_key)

        results = await asyncio.gather(*(extract(seg) for seg in segments))
        questions = _merge_extracted_segments(results)
        if not questions:
            raise QuizGenerationError("AI did not find any questions in the document")
        logger.info("bank_extracted_with_ai", segments=len(segments), questions=len(questions))
        return AIQuizResponse(
            title=self._title or "Generated Quiz",
            description=self._description or "Generated from uploaded file",
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

        collected: list[AIQuestion] = []
        title = ""
        description = ""
        semaphore = asyncio.Semaphore(GENERATION_MAX_CONCURRENCY)

        async def run_job(chunk_idx: int, count: int, focus, avoid: list[str]):
            async with semaphore:
                try:
                    result = await self._generate_raw(
                        chunks[chunk_idx], count, difficulty, question_type, language, avoid, focus
                    )
                except (AIProviderError, QuizGenerationError) as exc:
                    logger.warning("chunk_generation_failed", error=str(exc), requested=count)
                    return chunk_idx, None
                return chunk_idx, result

        for round_no in range(GENERATION_MAX_ROUNDS):
            missing = question_count - len(_usable(collected))
            if missing <= 0:
                break
            # The first round over-generates for deduplication headroom;
            # top-up rounds ask only for what's missing, starting at other chunks.
            wanted = math.ceil(missing * 1.25) + (0 if round_no == 0 else 1)
            avoid = [q.question for q in _usable(collected)][-MAX_AVOID_QUESTIONS:]
            jobs = _plan_generation_jobs(len(chunks), wanted, offset=round_no)
            results = await asyncio.gather(*(run_job(idx, n, focus, avoid) for idx, n, focus in jobs))

            for chunk_idx, result in results:
                if result is None:
                    continue
                if not title:
                    title = result.title
                    description = result.description
                chunk_link = _find_source_link(chunks[chunk_idx])
                if chunk_link:
                    for q in result.questions:
                        q.source_link = chunk_link
                collected.extend(result.questions)
            logger.info(
                "generation_round_done",
                round=round_no + 1,
                jobs=len(jobs),
                usable=len(_usable(collected)),
                target=question_count,
            )

        if not collected:
            raise QuizGenerationError("AI failed to generate any valid questions from the document")

        final_questions = _clean_generated(collected)[:question_count]

        if not final_questions:
            raise QuizGenerationError("No valid questions remained after deduplication")

        return AIQuizResponse(
            title=title or "Generated Quiz",
            description=description or "Generated from uploaded PDF",
            questions=final_questions,
        )

    async def generate_from_topic(
        self, topic: str, question_count: int, difficulty: str, question_type: str, language: str
    ) -> AIQuizResponse:
        """Topic-only generation from the model's own knowledge. Used to go
        through generate_from_chunks with the topic as the "source text",
        which clashed with that prompt's "use ONLY the source material" rule
        and produced thin, often wrong questions."""
        messages = build_topic_messages(
            topic=topic,
            question_count=math.ceil(question_count * 1.3),
            difficulty=difficulty,
            question_type=question_type,
            language=language,
        )
        result = await self._complete_and_parse(messages, temperature=GENERATION_TEMPERATURE)
        final_questions = _clean_generated(result.questions)[:question_count]
        if not final_questions:
            raise QuizGenerationError("No valid questions remained after deduplication")
        return AIQuizResponse(title=result.title, description=result.description, questions=final_questions)
