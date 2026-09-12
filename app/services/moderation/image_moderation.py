import base64

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# OpenAI's moderation endpoint is free to use (unlike chat completions) and
# works independently of FEATURE_PDF_AI_CREATION_ENABLED, so it stays on even
# while AI-assisted quiz generation is disabled for billing reasons.
_MODERATION_MODEL = "omni-moderation-latest"

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if settings.ai_provider != "openai" or not settings.ai_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)
    return _client


async def is_image_flagged(image_bytes: bytes) -> bool:
    """True if the image should be rejected (sexual/explicit/graphic content
    etc.). Fails OPEN (returns False) on any moderation-API error — a
    transient outage should never block someone from creating a quiz."""
    client = _get_client()
    if client is None:
        return False

    try:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        result = await client.moderations.create(
            model=_MODERATION_MODEL,
            input=[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}],
        )
        entry = result.results[0]
        if entry.flagged:
            flagged_categories = [name for name, value in entry.categories.model_dump().items() if value]
            logger.warning("image_moderation_flagged", categories=flagged_categories)
        return entry.flagged
    except Exception as exc:
        logger.warning("image_moderation_error", error=str(exc))
        return False
