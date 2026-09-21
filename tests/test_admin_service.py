import asyncio

import pytest

from app.services.admin import admin_service


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Stands in for AsyncSession: BotAdminRepository.list_telegram_ids only
    ever does a single `select(...)` execute, so returning a canned row list
    is enough to exercise the caching logic."""

    def __init__(self, rows):
        self.rows = rows
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        return _FakeResult(self.rows)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    admin_service.invalidate_cache()
    monkeypatch.setattr(admin_service.settings, "admin_ids", "111,222")
    yield
    admin_service.invalidate_cache()


def test_env_ids_are_owners_and_always_admins():
    assert admin_service.owner_ids() == {111, 222}
    assert admin_service.is_owner(111) is True
    assert admin_service.is_owner(999) is False
    # An owner needs no database lookup at all.
    assert asyncio.run(admin_service.is_admin(None, 111)) is True


def test_database_admin_is_recognised():
    session = _FakeSession([333])
    assert asyncio.run(admin_service.is_admin(session, 333)) is True
    assert asyncio.run(admin_service.is_admin(session, 444)) is False


def test_all_admin_ids_merges_owners_and_database_rows():
    session = _FakeSession([333])
    assert asyncio.run(admin_service.all_admin_ids(session)) == {111, 222, 333}


def test_lookup_is_cached_until_invalidated():
    session = _FakeSession([333])
    asyncio.run(admin_service.is_admin(session, 333))
    asyncio.run(admin_service.is_admin(session, 333))
    assert session.execute_calls == 1

    admin_service.invalidate_cache()
    session.rows = []
    assert asyncio.run(admin_service.is_admin(session, 333)) is False
    assert session.execute_calls == 2


def test_no_session_falls_back_to_owners_only():
    assert asyncio.run(admin_service.is_admin(None, 333)) is False
    assert asyncio.run(admin_service.all_admin_ids(None)) == {111, 222}
