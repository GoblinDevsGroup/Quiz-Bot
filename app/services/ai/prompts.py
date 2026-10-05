from app.schemas.ai import AIChatMessage

# Spelled out instead of passing a bare code: "uz" alone left models free to
# answer in Cyrillic Uzbek or drift into Russian/English mid-quiz.
LANGUAGE_NAMES = {
    "uz": "Uzbek (Latin script, modern O'zbek lotin alifbosi)",
    "ru": "Russian",
    "en": "English",
}

_QUALITY_RULES = """QUALITY RULES:
- Exactly one option is correct. Before writing correct_option, solve the question yourself step by step
  (in the "explanation" field) and double-check the answer; if you are not certain, drop the question.
- Every distractor must be clearly wrong, yet plausible to someone who has not learned the material
  (common misconceptions, near-miss values, related but wrong terms). No joke options.
- Options must be similar in length, style and grammatical form, so the correct one does not stand out.
- No duplicate or overlapping options, and never "all of the above" / "none of the above" / "both A and B".
- Each question is self-contained: never refer to "the text", "the passage", "the document" or "above".
- Ask about meaningful facts, concepts, cause-and-effect and application — not trivia such as page numbers,
  author names or the order in which things were listed.
- Keep questions short and unambiguous (Telegram shows at most 300 characters for a question and 100 per option).
- No two questions may test the same fact.
- Return valid JSON only, matching the requested schema exactly. No markdown, no commentary.
"""

SYSTEM_PROMPT = f"""You are an experienced teacher and exam author who writes accurate multiple-choice tests.

TASK:
Generate multiple-choice questions based ONLY on the provided source material.

SOURCE RULES:
- Do not invent facts that are not present in the source material.
- Every question must be answerable strictly from the source text.
- Follow the requested output language strictly, including for options and explanations.
- Follow the requested difficulty distribution.
- Each question has 4 options, unless "true_false" type is requested, in which case use exactly 2 options
  ("True"/"False" translated to the requested language).

{_QUALITY_RULES}"""

TOPIC_SYSTEM_PROMPT = f"""You are an experienced teacher and exam author who writes accurate multiple-choice tests.

TASK:
Generate multiple-choice questions about the topic the user gives, using well-established, textbook-level
knowledge. Only ask about facts that are settled and that you are sure of; skip anything disputed,
recent, or that you would have to guess.

RULES:
- Follow the requested output language strictly, including for options and explanations.
- Follow the requested difficulty distribution.
- Each question has 4 options, unless "true_false" type is requested, in which case use exactly 2 options
  ("True"/"False" translated to the requested language).

{_QUALITY_RULES}"""

# "explanation" is deliberately placed before "correct_option": models write
# JSON fields in order, so this makes them reason about the answer first and
# only then commit to an index, instead of picking an index and rationalising.
RESPONSE_SCHEMA_HINT = """
Respond with a single JSON object of this exact shape (keep the field order):
{
  "title": "string, short quiz title",
  "description": "string, one sentence description",
  "questions": [
    {
      "question": "string",
      "options": ["string", "string", ...],
      "explanation": "string, 1-2 sentences: why the correct option is right",
      "correct_option": 0,
      "difficulty": "easy" | "medium" | "hard"
    }
  ]
}
"""


def _language_line(language: str) -> str:
    if language == "auto":
        return "Detect the dominant language of the source text and write the quiz in that language."
    name = LANGUAGE_NAMES.get(language, language)
    return f"Write the whole quiz strictly in {name}."


def _difficulty_line(difficulty: str) -> str:
    if difficulty == "mixed":
        return "Mix easy, medium and hard questions roughly evenly."
    return f"All questions should be '{difficulty}' difficulty."


def _type_line(question_type: str) -> str:
    if question_type == "mixed":
        return "Mostly multiple-choice questions with 4 options; at most a quarter may be true/false."
    return f"All questions must be of type '{question_type}'."


def build_generation_messages(
    *,
    source_text: str,
    question_count: int,
    difficulty: str,
    question_type: str,
    language: str,
) -> list[AIChatMessage]:
    user_prompt = f"""
Generate exactly {question_count} quiz questions from the following source material.

{_difficulty_line(difficulty)}
{_type_line(question_type)}
{_language_line(language)}

{RESPONSE_SCHEMA_HINT}

SOURCE MATERIAL:
\"\"\"
{source_text}
\"\"\"
"""
    return [
        AIChatMessage(role="system", content=SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]


def build_topic_messages(*, topic: str, question_count: int, difficulty: str, question_type: str, language: str) -> list[AIChatMessage]:
    user_prompt = f"""
Generate exactly {question_count} quiz questions about this topic: {topic}

{_difficulty_line(difficulty)}
{_type_line(question_type)}
{_language_line(language)}

{RESPONSE_SCHEMA_HINT}
"""
    return [
        AIChatMessage(role="system", content=TOPIC_SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]


def build_repair_messages(broken_json: str, error: str) -> list[AIChatMessage]:
    user_prompt = f"""
The following JSON is invalid or does not match the required schema.

ERROR: {error}

JSON:
{broken_json}

Fix it and return ONLY the corrected valid JSON object matching this schema:
{RESPONSE_SCHEMA_HINT}
"""
    return [
        AIChatMessage(role="system", content="You fix malformed JSON. Return valid JSON only, no commentary."),
        AIChatMessage(role="user", content=user_prompt),
    ]


BANK_SYSTEM_PROMPT = """You convert existing test questions from a document into structured quiz JSON.

RULES:
- Keep each question's original wording, original language and original option order. Do not rewrite or translate.
- Remove numbering ("12.") and option letters ("A)") from the text.
- "correct_option" is the 0-based index of the correct option.
  * If the document gives the answer (e.g. "Javob: B", "Ответ: B", a trailing answer key, a starred,
    bold or "+"-marked option), use it exactly — it overrides your own opinion.
  * Otherwise solve the question yourself, carefully and step by step, in the "explanation" field first
    (for numbered-statement questions like "1. ... 2. ... 3. ..." check every statement separately), and
    only then set correct_option to the option that matches your solution.
- "explanation": 1-2 short sentences justifying the answer, in the question's language.
- Return questions in the same order as given, one JSON question per input question.
- If an input question has fewer than 2 options, skip it.
- Return valid JSON only. No markdown, no commentary.
"""


def build_bank_conversion_messages(*, question_blocks: list[str], answer_key: str) -> list[AIChatMessage]:
    numbered = "\n\n".join(question_blocks)
    key_section = f"\nANSWER KEY FROM THE DOCUMENT:\n\"\"\"\n{answer_key}\n\"\"\"\n" if answer_key else ""
    user_prompt = f"""
Convert the following {len(question_blocks)} existing test questions into quiz JSON.
{key_section}
{RESPONSE_SCHEMA_HINT}

QUESTIONS:
\"\"\"
{numbered}
\"\"\"
"""
    return [
        AIChatMessage(role="system", content=BANK_SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]
