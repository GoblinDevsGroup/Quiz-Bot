from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPkMixin


class Category(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_uz: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name_ru: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    quizzes: Mapped[list["Quiz"]] = relationship(back_populates="category")
    subject_groups: Mapped[list["SubjectGroup"]] = relationship(back_populates="category", cascade="all, delete-orphan")

    def localized_name(self, locale: str) -> str:
        return {"uz": self.name_uz, "ru": self.name_ru, "en": self.name_en}.get(locale) or self.name
