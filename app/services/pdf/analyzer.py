import re
from dataclasses import dataclass, field
from typing import Optional

# A line that starts a numbered question: "12. text" or "12) text".
_QUESTION_START_RE = re.compile(r"^[ \t]*(\d{1,4})[ \t]*[.)][ \t]*(?=\S)", re.MULTILINE)
# An answer option marker: "A) text", "b. text", "(C) text" (Latin or Cyrillic letters).
# Matched anywhere a new option can start (line start, or after whitespace),
# not only at the start of a line, since some documents cram all options
# ("A) ... B) ... C) ... D) ...") onto a single line.
_OPTION_MARK_RE = re.compile(r"(?:^|(?<=\s))\**\(?([A-Da-dА-Га-г])[.)](?=[ \t])", re.MULTILINE)
# Heading that introduces an answer key at the end of a question bank.
_ANSWER_KEY_HEADING_RE = re.compile(
    r"^[ \t]*[^\n]{0,15}\b(javoblar|javob|kalit|ответы|ответ|ключ|answers|answer key|key)\b[^\n]{0,25}$",
    re.IGNORECASE | re.MULTILINE,
)
# Heading that introduces a new exam variant/sheet, whose questions restart
# numbering at 1 (e.g. "Variant- 2", "Вариант 3").
_VARIANT_HEADING_RE = re.compile(r"\b(variant|вариант)\b", re.IGNORECASE)

# One "number -> letter" pair inside an answer key: "1-A", "2.b", "3) C", "4 Г".
_KEY_PAIR_RE = re.compile(r"(\d{1,4})[ \t]*[-–.):=]?[ \t]*([A-Da-dА-Га-г])(?![A-Za-zА-Яа-яЁё'])")
# An answer given right inside the question block: "Javob: B", "Ответ: в".
_INLINE_ANSWER_RE = re.compile(
    r"\b(?:to'g'ri javob|javob|ответ|answer)[ \t]*[:\-–]?[ \t]*\(?([A-Da-dА-Га-г])\)?(?![A-Za-zА-Яа-яЁё'])",
    re.IGNORECASE,
)
# Cyrillic option letters follow А Б В Г order, so Cyrillic "В" is the
# THIRD option even though it looks like Latin "B".
_LETTER_INDEX = {
    **{c: i for i, c in enumerate("ABCD")},
    **{c: i for i, c in enumerate("abcd")},
    **{c: i for i, c in enumerate("АБВГ")},
    **{c: i for i, c in enumerate("абвг")},
}

MIN_QUESTIONS_FOR_BANK = 5
MIN_OPTION_SHARE = 0.6
MATERIAL_MAX_QUESTIONS = 100
CHARS_PER_MATERIAL_QUESTION = 400

_ALL_WORDS = {"all", "hammasi", "barchasi", "hamma", "все", "всё", "barcha"}
_RANGE_RE = re.compile(r"^(\d{1,4})\s*[-–—:]\s*(\d{1,4})$")


@dataclass
class DocumentAnalysis:
    is_question_bank: bool
    blocks: list[str] = field(default_factory=list)
    answer_key: str = ""
    total_chars: int = 0
    # Per block: the 0-based correct option taken straight from the document
    # (answer key or an inline "Javob: B"), or None when the document doesn't
    # say. Applied over the AI's own choice, which can't be trusted to map a
    # key correctly — especially in files with several "Variant" sheets that
    # all restart numbering at 1.
    answers: list[Optional[int]] = field(default_factory=list)

    @property
    def question_count(self) -> int:
        return len(self.blocks)

    @property
    def max_selectable(self) -> int:
        """How many questions the user may ask for from this document."""
        if self.is_question_bank:
            return len(self.blocks)
        estimated = self.total_chars // CHARS_PER_MATERIAL_QUESTION
        return max(5, min(MATERIAL_MAX_QUESTIONS, estimated))


def _find_question_starts(text: str) -> list[tuple[int, int, int]]:
    """Find where each question of a 1, 2, 3... numbered chain starts, as
    (offset, question_number, variant_index); stray numbers stay inside their block.

    A candidate number only starts a new block once the *current* block has
    already shown at least one answer-option mark (A)/B)/C)/D)). Without
    this, a question's own nested fact list ("1) ...; 2) ...; 3) ...")
    inside its stem can happen to match the expected question sequence and
    get mistaken for the next question, chopping it apart mid-stem.

    Files that bundle several "Variant N" exam sheets restart their question
    numbering back at 1 for each variant. When a "Variant" heading appears
    between the previous question and a "1", that "1" is accepted as the
    start of the new variant even though a different number was expected.
    """
    starts: list[tuple[int, int, int]] = []
    expected = 1
    variant = 0
    for match in _QUESTION_START_RE.finditer(text):
        n = int(match.group(1))
        gap = text[starts[-1][0] : match.start()] if starts else ""
        block_closed = bool(starts) and bool(_OPTION_MARK_RE.search(gap))
        if n == expected:
            if starts and not block_closed:
                continue
        elif n == 1 and block_closed and _VARIANT_HEADING_RE.search(gap):
            variant += 1
        else:
            continue
        starts.append((match.start(), n, variant))
        expected = n + 1
    return starts


def _split_answer_key(last_block: str) -> tuple[str, str]:
    """Detach a trailing 'Answers: 1-A 2-B ...' section from the final question."""
    match = _ANSWER_KEY_HEADING_RE.search(last_block)
    if not match or match.start() == 0:
        return last_block, ""
    return last_block[: match.start()].strip(), last_block[match.start():].strip()


def _parse_key_pairs(key_text: str) -> dict[int, int]:
    return {int(num): _LETTER_INDEX[letter] for num, letter in _KEY_PAIR_RE.findall(key_text)}


def _parse_answer_key(key_text: str) -> list[dict[int, int]]:
    """One {question_number: option_index} dict per variant section of the key."""
    cuts = [m.start() for m in _VARIANT_HEADING_RE.finditer(key_text)]
    bounds = [0] + cuts + [len(key_text)]
    sections = [_parse_key_pairs(key_text[a:b]) for a, b in zip(bounds, bounds[1:])]
    return [sec for sec in sections if sec]


def analyze_document(text: str) -> DocumentAnalysis:
    starts = _find_question_starts(text)
    if len(starts) < MIN_QUESTIONS_FOR_BANK:
        return DocumentAnalysis(False, [], "", len(text))

    ends = [s for s, _, _ in starts[1:]] + [len(text)]
    blocks = [text[s:e].strip() for (s, _, _), e in zip(starts, ends)]
    with_options = sum(1 for b in blocks if len(set(_OPTION_MARK_RE.findall(b))) >= 2)
    if with_options / len(blocks) < MIN_OPTION_SHARE:
        return DocumentAnalysis(False, [], "", len(text))

    # An answer key can follow the whole file or each variant sheet, so try
    # to detach one from the last question of every variant.
    variant_count = starts[-1][2] + 1
    key_texts: list[str] = []
    for i, (_, _, variant) in enumerate(starts):
        is_variant_end = i == len(starts) - 1 or starts[i + 1][2] != variant
        if is_variant_end:
            body, key_text = _split_answer_key(blocks[i])
            if key_text and not _parse_key_pairs(key_text) and _INLINE_ANSWER_RE.search(key_text):
                continue  # just this question's own "Javob: B" line, not a key
            blocks[i] = body
            if key_text:
                key_texts.append(key_text)

    keys = [k for kt in key_texts for k in _parse_answer_key(kt)]
    if len(keys) != variant_count:
        # Can't tell which key belongs to which variant — let the AI decide.
        keys = []

    answers: list[Optional[int]] = []
    for block, (_, number, variant) in zip(blocks, starts):
        inline = _INLINE_ANSWER_RE.search(block)
        if inline:
            answers.append(_LETTER_INDEX[inline.group(1)])
        elif keys:
            answers.append(keys[variant].get(number))
        else:
            answers.append(None)

    return DocumentAnalysis(True, blocks, "\n\n".join(key_texts), len(text), answers)


def parse_selection(raw: str, analysis: DocumentAnalysis) -> tuple[int, int] | None:
    """Turn '30', '1-50' or 'hammasi' into an inclusive 1-based (start, end), or None if invalid."""
    value = raw.strip().lower()
    limit = analysis.max_selectable

    if value in _ALL_WORDS:
        return 1, limit

    if value.isdigit():
        count = int(value)
        return (1, count) if 1 <= count <= limit else None

    match = _RANGE_RE.match(value)
    if match and analysis.is_question_bank:
        start, end = int(match.group(1)), int(match.group(2))
        if 1 <= start <= end <= limit:
            return start, end
    return None
