"""FamilyMember CRUD services (PRD Section 10.3)."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.family_member.models import FamilyMember


def list_family_members(db: DbSession) -> list[FamilyMember]:
    return list(db.scalars(select(FamilyMember).order_by(FamilyMember.name)).all())


def get_family_member(db: DbSession, member_id: int) -> FamilyMember | None:
    return db.get(FamilyMember, member_id)


def create_family_member(
    db: DbSession, name: str, notes: str | None, school_days: Iterable[str]
) -> FamilyMember:
    member = FamilyMember(
        name=name.strip(),
        notes=notes.strip() if notes else None,
        school_days=list(school_days),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def update_family_member(
    db: DbSession,
    member_id: int,
    name: str,
    notes: str | None,
    school_days: Iterable[str],
) -> FamilyMember | None:
    member = db.get(FamilyMember, member_id)
    if member is None:
        return None
    member.name = name.strip()
    member.notes = notes.strip() if notes else None
    member.school_days = list(school_days)
    db.commit()
    db.refresh(member)
    return member


def delete_family_member(db: DbSession, member_id: int) -> bool:
    member = db.get(FamilyMember, member_id)
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True
