import os
import secrets
import uuid
from pathlib import Path

PDF_MAGIC = b"%PDF-"


def generate_safe_filename(extension: str = ".pdf") -> str:
    """Generate a random, path-traversal-safe filename. Never trust user-provided names."""
    token = secrets.token_hex(16)
    return f"{token}{extension}"


def safe_temp_path(base_dir: str, extension: str = ".pdf") -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    filename = generate_safe_filename(extension)
    path = (base / filename).resolve()
    if base.resolve() not in path.parents and path.parent != base.resolve():
        raise ValueError("Unsafe path resolution detected")
    return path


def is_pdf_signature(data: bytes) -> bool:
    return data[:5] == PDF_MAGIC


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def cleanup_file(path: os.PathLike) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
