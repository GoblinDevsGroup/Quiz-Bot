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
