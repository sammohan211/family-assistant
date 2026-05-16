"""Database engine, session, and declarative base."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from family_assistant.settings import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
engine = create_engine(_settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped DB session."""
    with SessionLocal() as session:
        yield session
