from typing import Optional

from langdetect import LangDetectException, detect

CHUNK_TARGET_CHARS = 6000
CHUNK_OVERLAP_CHARS = 200
MAX_CHUNKS = 8


def detect_language(text: str) -> Optional[str]:
    try:
        return detect(text[:5000])
    except LangDetectException:
        return None


def split_into_chunks(text: str, target_chars: int = CHUNK_TARGET_CHARS) -> list[str]:
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

    if len(chunks) > MAX_CHUNKS:
        # Keep coverage across the whole document rather than only the start.
        step = len(chunks) / MAX_CHUNKS
        chunks = [chunks[int(i * step)] for i in range(MAX_CHUNKS)]

    return chunks or [text[:target_chars]]
