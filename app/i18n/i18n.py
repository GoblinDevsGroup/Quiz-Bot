import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED_LOCALES = ("uz", "ru", "en")
DEFAULT_LOCALE = "uz"


@lru_cache
def _load_locale(locale: str) -> dict:
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        path = LOCALES_DIR / f"{DEFAULT_LOCALE}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def t(locale: str, key: str, **kwargs) -> str:
    locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    strings = _load_locale(locale)
    template = strings.get(key) or _load_locale(DEFAULT_LOCALE).get(key, key)
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


class Translator:
    """Bound to a specific user's locale for ergonomic repeated calls."""

    def __init__(self, locale: str):
        self.locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE

    def __call__(self, key: str, **kwargs) -> str:
        return t(self.locale, key, **kwargs)
