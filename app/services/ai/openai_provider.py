from openai import AsyncOpenAI, APIError, APITimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.ai import AIChatMessage
from app.services.ai.base import AIProvider, AIProviderError

logger = get_logger(__name__)


class OpenAIProvider(AIProvider):
    """Works with OpenAI and any OpenAI-compatible API (set AI_BASE_URL)."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
            timeout=settings.ai_request_timeout,
        )
        self._model = settings.ai_model
        # Some newer models (e.g. the gpt-6 reasoning family) reject any
        # non-default temperature outright. Once we learn that from a live
        # 400 response, stop sending it for the rest of this process instead
        # of failing every request forever.
        self._temperature_unsupported = False

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((APITimeoutError, AIProviderError)),
    )
    async def complete(
        self,
        messages: list[AIChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 4000,
        response_format_json: bool = True,
    ) -> str:
        try:
            kwargs = {}
            if response_format_json:
                kwargs["response_format"] = {"type": "json_object"}
            if not self._temperature_unsupported:
                kwargs["temperature"] = temperature

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[m.model_dump() for m in messages],
                max_completion_tokens=max_tokens,
                **kwargs,
            )
            content = response.choices[0].message.content
            if not content:
                raise AIProviderError("Empty AI response")
            return content
        except APIError as exc:
            if "temperature" in str(exc) and not self._temperature_unsupported:
                self._temperature_unsupported = True
                logger.warning("ai_model_rejects_temperature", model=self._model)
            else:
                logger.error("ai_provider_error", error=str(exc))
            raise AIProviderError(str(exc)) from exc
