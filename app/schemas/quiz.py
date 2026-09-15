import uuid
from typing import Optional

from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    text: str
    options: list[str]
    correct_option_index: int
    explanation: Optional[str] = None
    difficulty: str = "medium"
    question_type: str = "multiple_choice"
    image_file_id: Optional[str] = None
    source_link: Optional[str] = None


class QuizCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    grade: Optional[int] = None
    difficulty: str = "mixed"
    visibility: str = "private"
    language: str = "uz"
    time_limit_seconds: Optional[int] = None
    shuffle_questions: bool = False
    shuffle_options: bool = False
    questions: list[QuestionCreate] = Field(default_factory=list)


class GenerationSettings(BaseModel):
    question_count: int = Field(default=10, ge=1, le=50)
    difficulty: str = "mixed"
    question_type: str = "mixed"
    language: str = "auto"
