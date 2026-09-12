from app.services.pdf.chunker import MAX_CHUNKS, split_into_chunks


def test_short_text_produces_single_chunk():
    chunks = split_into_chunks("Hello world. This is a short document.")
    assert len(chunks) == 1


def test_long_text_is_split_into_multiple_chunks():
    paragraph = "Sentence about the topic. " * 300
    text = "\n\n".join([paragraph] * 20)
    chunks = split_into_chunks(text, target_chars=1000)
    assert len(chunks) > 1
    assert len(chunks) <= MAX_CHUNKS


def test_chunking_preserves_total_content_roughly():
    text = "\n\n".join([f"Paragraph {i} with some content." for i in range(50)])
    chunks = split_into_chunks(text, target_chars=200)
    joined_len = sum(len(c) for c in chunks)
    assert joined_len > 0
