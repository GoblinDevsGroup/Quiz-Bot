from openai import AsyncOpenAI, APIError, APITimeoutError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.ai import AIChatMessage
from app.services.ai.base import AIProvider, AIProviderError, AIResponseTruncatedError

logger = get_logger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    # A truncated answer would just be truncated again; let the caller split the work.
    if isinstance(exc, AIResponseTruncatedError):
        return False
    return isinstance(exc, (APITimeoutError, AIProviderError))


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
        # Optional (AI_REASONING_EFFORT). Reasoning models get answer keys
        # noticeably more often right when allowed to think first; models
        # that don't support the parameter get it dropped the same way as
        # temperature above.
        self._reasoning_effort = settings.ai_reasoning_effort or None

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
    )
    async def complete(
        self,
        messages: list[AIChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 16000,
        response_format_json: bool = True,
    ) -> str:
        try:
            kwargs = {}
            if response_format_json:
                kwargs["response_format"] = {"type": "json_object"}
            if not self._temperature_unsupported:
                kwargs["temperature"] = temperature
            if self._reasoning_effort:
                kwargs["reasoning_effort"] = self._reasoning_effort

            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[m.model_dump() for m in messages],
                max_completion_tokens=max_tokens,
                **kwargs,
            )
            choice = response.choices[0]
            content = choice.message.content
            if choice.finish_reason == "length":
                # Reasoning models count their hidden thinking against
                # max_completion_tokens; a big request can use it all up and
                # come back empty or with cut-off JSON.
                logger.warning("ai_response_truncated", model=self._model, has_content=bool(content))
                raise AIResponseTruncatedError("AI response hit the token limit")
            if not content:
                raise AIProviderError("Empty AI response")
            return content
        except APIError as exc:
            if "temperature" in str(exc) and not self._temperature_unsupported:
                self._temperature_unsupported = True
                logger.warning("ai_model_rejects_temperature", model=self._model)
            elif "reasoning" in str(exc) and self._reasoning_effort:
                self._reasoning_effort = None
                logger.warning("ai_model_rejects_reasoning_effort", model=self._model)
            else:
                logger.error("ai_provider_error", error=str(exc))
            raise AIProviderError(str(exc)) from exc
