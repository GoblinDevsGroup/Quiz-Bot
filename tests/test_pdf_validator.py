import pytest

from app.services.pdf.validator import PdfValidationError, validate_pdf_upload


def test_valid_pdf_passes():
    validate_pdf_upload(file_size=1000, mime_type="application/pdf", header_bytes=b"%PDF-1.7")


def test_rejects_empty_file():
    with pytest.raises(PdfValidationError):
        validate_pdf_upload(file_size=0, mime_type="application/pdf", header_bytes=b"%PDF-1.7")


def test_rejects_oversized_file():
    from app.core.config import settings

    with pytest.raises(PdfValidationError):
        validate_pdf_upload(
            file_size=settings.pdf_max_size_bytes + 1, mime_type="application/pdf", header_bytes=b"%PDF-1.7"
        )


def test_rejects_wrong_mime_type():
    with pytest.raises(PdfValidationError):
        validate_pdf_upload(file_size=1000, mime_type="image/png", header_bytes=b"%PDF-1.7")


def test_rejects_missing_pdf_signature():
    with pytest.raises(PdfValidationError):
        validate_pdf_upload(file_size=1000, mime_type="application/pdf", header_bytes=b"NOT_A_PDF")
