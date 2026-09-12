from abc import ABC, abstractmethod

from app.schemas.ai import AIChatMessage


class AIProvider(ABC):
    """Abstraction over any OpenAI-compatible chat completion backend.

    Implementations must accept a list of chat messages and return raw
    text content. Provider-specific SDK/API details stay behind this
    interface so a new backend can be added without touching callers.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[AIChatMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 4000,
        response_format_json: bool = True,
    ) -> str:
        raise NotImplementedError


class AIProviderError(Exception):
    pass
