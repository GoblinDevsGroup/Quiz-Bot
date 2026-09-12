from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AIQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    options: list[str] = Field(..., min_length=2, max_length=6)
    correct_option: int = Field(..., ge=0)
    explanation: str = Field(default="", max_length=1000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"

    @field_validator("options")
    @classmethod
    def _non_empty_options(cls, v: list[str]) -> list[str]:
        cleaned = [o.strip() for o in v if o and o.strip()]
        if len(cleaned) < 2:
            raise ValueError("At least 2 non-empty options required")
        return cleaned

    @model_validator(mode="after")
    def _correct_index_in_range(self) -> "AIQuestion":
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option index out of range")
        return self


class AIQuizResponse(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field(default="", max_length=1000)
    questions: list[AIQuestion] = Field(..., min_length=1)


class AIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
