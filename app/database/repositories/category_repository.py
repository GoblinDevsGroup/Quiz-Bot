import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Category

DEFAULT_CATEGORIES = [
    ("Programming", "Dasturlash", "Программирование", "💻"),
    ("Mathematics", "Matematika", "Математика", "🔢"),
    ("Physics", "Fizika", "Физика", "⚛️"),
    ("Chemistry", "Kimyo", "Химия", "🧪"),
    ("Biology", "Biologiya", "Биология", "🧬"),
    ("History", "Tarix", "История", "📜"),
    ("Geography", "Geografiya", "География", "🌍"),
    ("Languages", "Tillar", "Языки", "🗣️"),
    ("IT", "IT", "ИТ", "🖥️"),
    ("Business", "Biznes", "Бизнес", "💼"),
    ("Finance", "Moliya", "Финансы", "💰"),
    ("Law", "Huquq", "Право", "⚖️"),
    ("Medicine", "Tibbiyot", "Медицина", "🩺"),
    ("Other", "Boshqa", "Другое", "📦"),
]

# The fixed set of school-subject buttons shown when picking a subject for
# quiz creation or for browsing the quiz bank. Order here is the order the
# buttons are rendered in. Kept as (name_en, name_uz, name_ru, icon) to match
# DEFAULT_CATEGORIES's shape and to seed/backfill these rows regardless of
# what other (older) categories already exist in a given deployment.
CANONICAL_SUBJECTS = [
    ("Physics", "Fizika", "Физика", "⚛️"),
    ("Chemistry", "Kimyo", "Химия", "🧪"),
    ("Biology", "Biologiya", "Биология", "🧬"),
    ("Geography", "Geografiya", "География", "🌍"),
    ("History", "Tarix", "История", "📜"),
    ("English", "Ingliz tili", "Английский язык", "🇬🇧"),
    ("Native language", "Ona tili", "Родной язык", "🗣️"),
    ("General", "Umumiy", "Общее", "📦"),
]


class CategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[Category]:
        result = await self.session.execute(select(Category).order_by(Category.name))
        return list(result.scalars().all())

    async def get_by_id(self, category_id: uuid.UUID) -> Optional[Category]:
        return await self.session.get(Category, category_id)

    async def ensure_defaults(self) -> None:
        existing = await self.list_all()
        if existing:
            return
        for name_en, name_uz, name_ru, icon in DEFAULT_CATEGORIES:
            self.session.add(
                Category(name=name_en, name_en=name_en, name_uz=name_uz, name_ru=name_ru, icon=icon)
            )
        await self.session.flush()

    async def ensure_canonical_subjects(self) -> None:
        """Backfills the fixed school-subject categories (Fizika, Kimyo, ...)
        if they're missing — unlike ensure_defaults(), this always runs, so a
        database that already had other categories still gets these added."""
        result = await self.session.execute(select(Category.name_uz))
        existing_uz_names = {row[0] for row in result.all()}
        for name_en, name_uz, name_ru, icon in CANONICAL_SUBJECTS:
            if name_uz in existing_uz_names:
                continue
            self.session.add(
                Category(name=name_en, name_en=name_en, name_uz=name_uz, name_ru=name_ru, icon=icon)
            )
        await self.session.flush()

    async def get_canonical_subjects(self) -> list[Category]:
        """Returns the fixed subject categories in CANONICAL_SUBJECTS order —
        used to render the subject-picker keyboard consistently regardless of
        row insertion order in the database."""
        result = await self.session.execute(select(Category))
        by_name_uz = {c.name_uz: c for c in result.scalars().all()}
        return [by_name_uz[name_uz] for _, name_uz, _, _ in CANONICAL_SUBJECTS if name_uz in by_name_uz]
