"""Database engine, session, and declarative base.

Engine and sessionmaker are built lazily on first use so that importing this
module (and the rest of the app — every model imports `Base` from here) does
not require a populated `.env`. Configuration errors surface at startup or at
first DB access, not during module import or test collection.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from family_assistant.settings import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped DB session."""
    with get_sessionmaker()() as session:
        yield session
