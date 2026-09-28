import re
from dataclasses import dataclass, field

# A line that starts a numbered question: "12. text" or "12) text".
_QUESTION_START_RE = re.compile(r"^[ \t]*(\d{1,4})[ \t]*[.)][ \t]*(?=\S)", re.MULTILINE)
# An answer option line: "A) text", "b. text", "(C) text" (Latin or Cyrillic letters).
_OPTION_LINE_RE = re.compile(r"^[ \t]*\(?[A-Da-dА-Га-г][.)][ \t]+\S", re.MULTILINE)
# Heading that introduces an answer key at the end of a question bank.
_ANSWER_KEY_HEADING_RE = re.compile(
    r"^[ \t]*[^\n]{0,15}\b(javoblar|javob|kalit|ответы|ответ|ключ|answers|answer key|key)\b[^\n]{0,25}$",
    re.IGNORECASE | re.MULTILINE,
)

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


def _split_numbered_blocks(text: str) -> list[str]:
    """Split on a 1, 2, 3... numbered chain; stray numbers stay inside their block."""
    starts: list[int] = []
    expected = 1
    for match in _QUESTION_START_RE.finditer(text):
        if int(match.group(1)) == expected:
            starts.append(match.start())
            expected += 1
    if not starts:
        return []
    ends = starts[1:] + [len(text)]
    return [text[s:e].strip() for s, e in zip(starts, ends)]


def _split_answer_key(last_block: str) -> tuple[str, str]:
    """Detach a trailing 'Answers: 1-A 2-B ...' section from the final question."""
    match = _ANSWER_KEY_HEADING_RE.search(last_block)
    if not match or match.start() == 0:
        return last_block, ""
    return last_block[: match.start()].strip(), last_block[match.start():].strip()


def analyze_document(text: str) -> DocumentAnalysis:
    blocks = _split_numbered_blocks(text)
    if len(blocks) >= MIN_QUESTIONS_FOR_BANK:
        with_options = sum(1 for b in blocks if len(_OPTION_LINE_RE.findall(b)) >= 2)
        if with_options / len(blocks) >= MIN_OPTION_SHARE:
            blocks[-1], answer_key = _split_answer_key(blocks[-1])
            return DocumentAnalysis(True, blocks, answer_key, len(text))
    return DocumentAnalysis(False, [], "", len(text))


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
