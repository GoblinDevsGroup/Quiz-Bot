from app.schemas.ai import AIChatMessage

SYSTEM_PROMPT = """You are an expert educational quiz generator.

TASK:
Generate high-quality multiple-choice questions based ONLY on the provided source material.

RULES:
- Do not invent facts that are not present in the source material.
- Every question must be answerable strictly from the source text.
- Exactly one correct answer per question.
- Wrong answers (distractors) must be plausible, not obviously wrong.
- Avoid ambiguous or trick questions.
- Return valid JSON only, matching the requested schema exactly. No markdown, no commentary.
- Follow the requested output language strictly.
- Follow the requested difficulty distribution.
- Each question must have between 2 and 4 answer options unless "true_false" type is requested, in which case use exactly 2 options ("True"/"False" translated to the requested language).
"""

RESPONSE_SCHEMA_HINT = """
Respond with a single JSON object of this exact shape:
{
  "title": "string, short quiz title",
  "description": "string, one sentence description",
  "questions": [
    {
      "question": "string",
      "options": ["string", "string", ...],
      "correct_option": 0,
      "explanation": "string, short explanation citing the source",
      "difficulty": "easy" | "medium" | "hard"
    }
  ]
}
"""


def build_generation_messages(
    *,
    source_text: str,
    question_count: int,
    difficulty: str,
    question_type: str,
    language: str,
) -> list[AIChatMessage]:
    difficulty_line = (
        "Mix easy, medium and hard questions roughly evenly."
        if difficulty == "mixed"
        else f"All questions should be '{difficulty}' difficulty."
    )
    type_line = (
        "Mix multiple-choice and true/false questions."
        if question_type == "mixed"
        else f"All questions must be of type '{question_type}'."
    )
    language_line = (
        "Detect the dominant language of the source text and write the quiz in that language."
        if language == "auto"
        else f"Write the quiz strictly in this language code: {language}."
    )

    user_prompt = f"""
Generate exactly {question_count} quiz questions from the following source material.

{difficulty_line}
{type_line}
{language_line}

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
        AIChatMessage(role="system", content=SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]


BANK_SYSTEM_PROMPT = """You convert existing test questions from a document into structured quiz JSON.

RULES:
- Keep each question's original wording, original language and original option order. Do not rewrite or translate.
- Remove numbering ("12.") and option letters ("A)") from the text.
- "correct_option" is the 0-based index of the correct option. Use the answer key or marks in the document
  (e.g. "Javob: B", a trailing answer key, a highlighted/starred option) when present; otherwise choose the
  correct answer yourself.
- "explanation" is optional: one short sentence or an empty string.
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
