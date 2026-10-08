import re
from typing import Optional

from langdetect import LangDetectException, detect

CHUNK_TARGET_CHARS = 6000
CHUNK_OVERLAP_CHARS = 200
MAX_CHUNKS = 8

# A line that looks like the start of a numbered test question ("12. ..." / "12) ...").
_QUESTION_LINE_RE = re.compile(r"^[ \t]*\d{1,4}[ \t]*[.)]")


def detect_language(text: str) -> Optional[str]:
    try:
        return detect(text[:5000])
    except LangDetectException:
        return None


def split_into_chunks(text: str, target_chars: int = CHUNK_TARGET_CHARS, max_chunks: int = MAX_CHUNKS) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= target_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) > target_chars:
                for i in range(0, len(para), target_chars):
                    chunks.append(para[i : i + target_chars])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    if len(chunks) > max_chunks:
        # Keep coverage across the whole document rather than only the start.
        step = len(chunks) / max_chunks
        chunks = [chunks[int(i * step)] for i in range(max_chunks)]

    return chunks or [text[:target_chars]]


def split_into_segments(text: str, max_chars: int) -> list[str]:
    """Split the WHOLE text (nothing dropped) into pieces of at most ~max_chars,
    cutting right before a numbered question line where possible, so the AI
    rarely sees a test question torn in half between two pieces."""
    lines = text.splitlines(keepends=True)
    segments: list[str] = []
    current: list[str] = []
    size = 0

    for line in lines:
        if current and size + len(line) > max_chars:
            cut = _best_cut(current)
            segments.append("".join(current[:cut]))
            current = current[cut:]
            size = sum(len(x) for x in current)
        current.append(line)
        size += len(line)

    if current:
        segments.append("".join(current))
    return [s.strip() for s in segments if s.strip()]


def _best_cut(lines: list[str]) -> int:
    """Where to end a piece: before the last question line in its second
    half, else after the last blank line there, else at the very end."""
    min_keep = len(lines) // 2
    for i in range(len(lines) - 1, min_keep, -1):
        if _QUESTION_LINE_RE.match(lines[i]):
            return i
    for i in range(len(lines) - 1, min_keep, -1):
        if not lines[i].strip():
            return i
    return len(lines)
