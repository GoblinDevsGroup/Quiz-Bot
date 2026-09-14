import re

_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def is_http_url(text: str) -> bool:
    """True if `text` is a single bare http(s) URL with no other content."""
    return bool(_HTTP_URL_RE.match(text.strip()))
