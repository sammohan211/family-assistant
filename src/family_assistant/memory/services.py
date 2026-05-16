"""Memory CRUD + filtered listing (PRD Section 11.7).

Keyword search only in MVP; semantic search lands when the pgvector module does.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from family_assistant.auth.models import User
from family_assistant.memory.models import Memory

SUBJECT_TYPES = ("household", "user", "family_member")
MEMORY_TYPES = (
    "preference",
    "food_preference",
    "restriction",
    "routine",
    "planning_constraint",
    "frequently_used",
)
SOURCES = ("user", "assistant", "deployment_seed")


def normalize_subject(subject_type: str, subject_id: int | None) -> tuple[str, int | None]:
    if subject_type == "household":
        return "household", None
    return subject_type, subject_id


def parse_tags(raw: str) -> list[str]:
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def format_tags(tags: Iterable[str]) -> str:
    return ", ".join(tags)


def list_memories(
    db: DbSession,
    *,
    subject_type: str | None = None,
    subject_id: int | None = None,
    memory_type: str | None = None,
    query: str | None = None,
    tag: str | None = None,
    limit: int = 200,
) -> list[Memory]:
    statement = select(Memory).options(selectinload(Memory.created_by_user))
    if subject_type:
        statement = statement.where(Memory.subject_type == subject_type)
        if subject_type != "household" and subject_id is not None:
            statement = statement.where(Memory.subject_id == subject_id)
    if memory_type:
        statement = statement.where(Memory.memory_type == memory_type)
    if query:
        statement = statement.where(Memory.content.ilike(f"%{query}%"))
    if tag:
        statement = statement.where(Memory.tags.contains([tag]))
    statement = statement.order_by(
        Memory.is_hard_restriction.desc(),
        Memory.updated_at.desc(),
        Memory.id.desc(),
    ).limit(limit)
    return list(db.scalars(statement).all())


def get_memory(db: DbSession, memory_id: int) -> Memory | None:
    return db.get(Memory, memory_id)


def create_memory(
    db: DbSession,
    *,
    user: User | None,
    subject_type: str,
    subject_id: int | None,
    memory_type: str,
    content: str,
    is_hard_restriction: bool,
    tags: list[str],
    source: str = "user",
) -> Memory:
    subject_type, subject_id = normalize_subject(subject_type, subject_id)
    memory = Memory(
        subject_type=subject_type,
        subject_id=subject_id,
        memory_type=memory_type,
        content=content.strip(),
        is_hard_restriction=is_hard_restriction,
        source=source,
        tags=tags,
        created_by_user_id=user.id if user is not None else None,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def update_memory(
    db: DbSession,
    *,
    memory_id: int,
    subject_type: str,
    subject_id: int | None,
    memory_type: str,
    content: str,
    is_hard_restriction: bool,
    tags: list[str],
) -> Memory | None:
    memory = db.get(Memory, memory_id)
    if memory is None:
        return None
    subject_type, subject_id = normalize_subject(subject_type, subject_id)
    memory.subject_type = subject_type
    memory.subject_id = subject_id
    memory.memory_type = memory_type
    memory.content = content.strip()
    memory.is_hard_restriction = is_hard_restriction
    memory.tags = tags
    db.commit()
    db.refresh(memory)
    return memory


def delete_memory(db: DbSession, memory_id: int) -> bool:
    memory = db.get(Memory, memory_id)
    if memory is None:
        return False
    db.delete(memory)
    db.commit()
    return True
