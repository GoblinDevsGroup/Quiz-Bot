from functools import lru_cache

from app.core.config import settings
from app.services.ai.base import AIProvider
from app.services.ai.openai_provider import OpenAIProvider

_PROVIDERS = {
    "openai": OpenAIProvider,
    # Add more OpenAI-compatible or custom providers here, e.g.:
    # "azure_openai": AzureOpenAIProvider,
    # "local_llm": LocalLLMProvider,
}


@lru_cache
def get_ai_provider() -> AIProvider:
    provider_cls = _PROVIDERS.get(settings.ai_provider.lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported AI provider: {settings.ai_provider}")
    return provider_cls()
