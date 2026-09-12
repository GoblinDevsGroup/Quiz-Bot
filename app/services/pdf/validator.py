from app.core.config import settings
from app.core.security import is_pdf_signature


class PdfValidationError(Exception):
    pass


def validate_pdf_upload(*, file_size: int, mime_type: str | None, header_bytes: bytes) -> None:
    if file_size <= 0:
        raise PdfValidationError("Empty file")

    if file_size > settings.pdf_max_size_bytes:
        raise PdfValidationError(
            f"File too large: {file_size} bytes (max {settings.pdf_max_size_bytes} bytes)"
        )

    if mime_type and mime_type not in ("application/pdf", "application/x-pdf"):
        raise PdfValidationError(f"Unsupported MIME type: {mime_type}")

    if not is_pdf_signature(header_bytes):
        raise PdfValidationError("File does not have a valid PDF signature")
