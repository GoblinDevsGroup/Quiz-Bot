import re
from pathlib import Path

import fitz  # PyMuPDF

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER = 20


class PdfExtractionError(Exception):
    pass


class PdfExtractionResult:
    def __init__(self, text: str, page_count: int, used_ocr: bool):
        self.text = text
        self.page_count = page_count
        self.used_ocr = used_ocr


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    return text.strip()


def _ocr_page(page: "fitz.Page") -> str:
    try:
        import pytesseract
        from PIL import Image
        import io

        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

        pix = page.get_pixmap(dpi=200)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(image)
    except Exception as exc:  # OCR is best-effort; never crash the pipeline
        logger.warning("ocr_page_failed", error=str(exc))
        return ""


def extract_text(pdf_path: Path) -> PdfExtractionResult:
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PdfExtractionError(f"Could not open PDF: {exc}") from exc

    if doc.is_encrypted:
        try:
            doc.authenticate("")
        except Exception:
            raise PdfExtractionError("PDF is password-protected")

    page_texts: list[str] = []
    used_ocr = False

    for page in doc:
        text = page.get_text("text")
        if len(text.strip()) < MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER and settings.ocr_enabled:
            ocr_text = _ocr_page(page)
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
                used_ocr = True
        page_texts.append(text)

    page_count = doc.page_count
    doc.close()

    full_text = _clean_text("\n\n".join(page_texts))
    if not full_text:
        raise PdfExtractionError("No extractable text found in PDF, even after OCR")

    return PdfExtractionResult(text=full_text, page_count=page_count, used_ocr=used_ocr)
