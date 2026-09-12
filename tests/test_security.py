from pathlib import Path

from app.core.security import is_pdf_signature, safe_temp_path


def test_pdf_signature_detection():
    assert is_pdf_signature(b"%PDF-1.4\n...")
    assert not is_pdf_signature(b"GIF89a")


def test_safe_temp_path_is_random_and_within_base(tmp_path):
    base = tmp_path / "uploads"
    path1 = safe_temp_path(str(base), ".pdf")
    path2 = safe_temp_path(str(base), ".pdf")

    assert path1 != path2
    assert path1.suffix == ".pdf"
    assert base.resolve() in path1.parents


def test_safe_temp_path_ignores_user_filename(tmp_path):
    base = tmp_path / "uploads"
    path = safe_temp_path(str(base), ".pdf")
    assert "../" not in str(path)
    assert path.name != "malicious.pdf"
