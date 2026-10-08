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


def _avoid_section(avoid_questions: list[str] | None) -> str:
    if not avoid_questions:
        return ""
    listed = "\n".join(f"- {q[:150]}" for q in avoid_questions)
    return f"""
These questions already exist. Do NOT repeat them or ask about the same facts again — cover other facts:
{listed}
"""


def _focus_line(focus: tuple[int, int] | None) -> str:
    if not focus:
        return ""
    part, parts = focus
    return (
        f"Mentally split the source material into {parts} equal consecutive parts and take your questions "
        f"mainly from part {part} of {parts}, so parallel requests cover different facts."
    )


def build_generation_messages(
    *,
    source_text: str,
    question_count: int,
    difficulty: str,
    question_type: str,
    language: str,
    avoid_questions: list[str] | None = None,
    focus: tuple[int, int] | None = None,
) -> list[AIChatMessage]:
    user_prompt = f"""
Generate exactly {question_count} quiz questions from the following source material.

{_difficulty_line(difficulty)}
{_type_line(question_type)}
{_language_line(language)}
{_focus_line(focus)}
{_avoid_section(avoid_questions)}
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


BANK_EXTRACTION_SYSTEM_PROMPT = """You find ready-made test questions in raw text extracted from a PDF/DOCX file and
convert them into structured quiz JSON.

RULES:
- Return EVERY complete test question found in the text, in the original order. Do not skip any, do not merge two
  questions into one, do not invent new questions. A complete question has a question stem and at least 2 options.
- The text may be messy (broken lines, page headers/footers, tables flattened with "|"). Ignore that noise.
- Skip a fragment at the very START of the text that has options but no question stem (it was cut off from the
  previous piece). If the LAST question at the end is cut off before its options, skip it as well.
- Keep each question's original wording, original language and original option order. Do not rewrite or translate.
- Remove numbering ("12.") and option letters ("A)") from the text.
- "correct_option" is the 0-based index of the correct option.
  * If the document gives the answer (e.g. "Javob: B", "Ответ: B", an answer key, a starred, **bold** or
    "+"-marked option), use it exactly — it overrides your own opinion.
  * Otherwise solve the question yourself carefully in the "explanation" field first, then set correct_option.
- "explanation": 1-2 short sentences justifying the answer, in the question's language.
- Return valid JSON only. No markdown, no commentary.
"""


def build_bank_extraction_messages(*, text: str, answer_key: str) -> list[AIChatMessage]:
    key_section = f"\nANSWER KEY FROM THE DOCUMENT:\n\"\"\"\n{answer_key}\n\"\"\"\n" if answer_key else ""
    user_prompt = f"""
Extract all test questions from the text below and convert them into quiz JSON.
{key_section}
{RESPONSE_SCHEMA_HINT}

TEXT:
\"\"\"
{text}
\"\"\"
"""
    return [
        AIChatMessage(role="system", content=BANK_EXTRACTION_SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]


DOCUMENT_ANALYSIS_SYSTEM_PROMPT = """You inspect a piece of text extracted from a file a teacher uploaded to a quiz bot.
Your job is to COUNT accurately, not to write questions.

Return a JSON object:
{
  "kind": "test_bank" | "material",
  "questions": [{"label": "string", "start": "string"}],
  "material_capacity": 0
}

- "kind": "test_bank" when this text consists mainly of ready-made test questions with answer options
  (numbered or not). "material" when it is mainly study text (lecture, textbook, article, notes), even if it has a
  few example questions.
- "questions": one entry for EVERY ready-made test question in the text, in order: a question stem plus at least
  2 answer options. "label" is its number exactly as printed ("" if unnumbered), "start" is the first 5-6 words of
  its stem. Go through the text line by line — do not skip, merge, or estimate. Do not list items of a numbered
  list inside a question's stem, and do not list answer-key lines ("1-A 2-B ...") as questions.
  Skip a fragment at the very start of the text that has options but no stem.
- "material_capacity": how many distinct, good multiple-choice questions could be written from the study text
  (not the ready-made questions) here — roughly one per distinct definition, fact, rule, date, formula or example.
  0 if there is no study text.
- Return valid JSON only.
"""


def build_document_analysis_messages(text: str) -> list[AIChatMessage]:
    user_prompt = f"""
TEXT:
\"\"\"
{text}
\"\"\"
"""
    return [
        AIChatMessage(role="system", content=DOCUMENT_ANALYSIS_SYSTEM_PROMPT),
        AIChatMessage(role="user", content=user_prompt),
    ]
