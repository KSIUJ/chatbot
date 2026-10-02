"""Wyszukiwarka uzytkownikow dla panelu administratora: dane z Keycloaka,
dzisiejsze zuzycie dziennego limitu i wyjatek (jesli jest)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import DailyUsage, User, UserLimit
from .schemas import AdminUserItem, UserOverrideModel

# Znak ucieczki dla LIKE - % i _ z zapytania szukamy doslownie.
_LIKE_ESCAPE = "\\"


def _like_pattern(query: str) -> str:
    escaped = (
        query.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )
    return f"%{escaped.lower()}%"


def _filtered(query: str | None) -> Select[tuple[User]]:
    stmt = select(User)
    text = (query or "").strip()
    if text:
        pattern = _like_pattern(text)
        stmt = stmt.where(
            or_(
                func.lower(User.name).like(pattern, escape=_LIKE_ESCAPE),
                func.lower(User.username).like(pattern, escape=_LIKE_ESCAPE),
                func.lower(User.email).like(pattern, escape=_LIKE_ESCAPE),
            )
        )
    return stmt


def to_override_model(override: UserLimit | None) -> UserOverrideModel | None:
    if override is None:
        return None
    return UserOverrideModel(
        unlimited=override.daily_limit is None,
        daily_limit=override.daily_limit,
        note=override.note,
        updated_at=override.updated_at,
    )


def _item(user: User, used: int | None, override: UserLimit | None, global_limit: int) -> AdminUserItem:
    return AdminUserItem(
        id=user.id,
        name=user.name,
        username=user.username,
        email=user.email,
        last_login_at=user.last_login_at,
        used_today=int(used or 0),
        effective_limit=override.daily_limit if override is not None else global_limit,
        override=to_override_model(override),
    )


def search_users(
    db: Session, query: str | None, today: date, global_limit: int, limit: int, offset: int
) -> tuple[list[AdminUserItem], int]:
    """Strona uzytkownikow pasujacych do `query` (imie i nazwisko, login,
    email; bez rozrozniania wielkosci liter) wg nazwy, z dzisiejszym zuzyciem
    i wyjatkiem, oraz liczba wszystkich pasujacych.

    lower() w SQLite zmienia tylko litery ASCII - polskie litery z ogonkami
    i kreskami rozrozniaja wielkosc liter."""
    filtered = _filtered(query)
    total = db.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()

    sort_name = func.lower(func.coalesce(User.name, User.username, User.email, ""))
    page = (
        filtered.add_columns(DailyUsage.count.label("used_today"), UserLimit)
        .outerjoin(DailyUsage, and_(DailyUsage.user_id == User.id, DailyUsage.day == today))
        .outerjoin(UserLimit, UserLimit.user_id == User.id)
        .order_by(sort_name, User.id)
        .limit(limit)
        .offset(offset)
    )
    items = [_item(user, used, override, global_limit) for user, used, override in db.execute(page).tuples()]
    return items, int(total)


def user_item(db: Session, user: User, today: date, global_limit: int) -> AdminUserItem:
    """Jeden uzytkownik w formacie listy (odpowiedz po zmianie wyjatku)."""
    used = db.execute(
        select(DailyUsage.count).where(DailyUsage.user_id == user.id, DailyUsage.day == today)
    ).scalar_one_or_none()
    override = db.get(UserLimit, user.id, populate_existing=True)
    return _item(user, used, override, global_limit)
