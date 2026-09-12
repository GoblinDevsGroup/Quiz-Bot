from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    bot_token: str = Field(...)
    admin_ids: str = Field(default="")

    # Database
    database_url: str = Field(...)
    database_url_sync: str = Field(...)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_fsm_url: str = Field(default="redis://localhost:6379/1")

    # AI
    ai_provider: str = Field(default="openai")
    ai_api_key: str = Field(default="")
    ai_base_url: str = Field(default="https://api.openai.com/v1")
    ai_model: str = Field(default="gpt-4o-mini")
    ai_max_retries: int = Field(default=3)
    ai_request_timeout: int = Field(default=120)

    # PDF
    pdf_max_size_mb: int = Field(default=20)
    pdf_temp_dir: str = Field(default="/tmp/quizbot_pdf")
    ocr_enabled: bool = Field(default=True)
    tesseract_cmd: str = Field(default="tesseract")

    # Rate limiting
    rate_limit_messages_per_minute: int = Field(default=20)
    rate_limit_ai_per_hour: int = Field(default=5)

    # App
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    default_locale: str = Field(default="uz")

    @property
    def admin_id_list(self) -> List[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @field_validator("pdf_max_size_mb")
    @classmethod
    def _positive_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("pdf_max_size_mb must be positive")
        return v

    @property
    def pdf_max_size_bytes(self) -> int:
        return self.pdf_max_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Temporary feature flag: PDF- and AI-prompt-based quiz creation are disabled
# while OpenAI billing/testing is being sorted out, so only manual creation
# is offered. Flip back to True to restore the full method-selection menu.
FEATURE_PDF_AI_CREATION_ENABLED = False
