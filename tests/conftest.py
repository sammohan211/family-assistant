"""Pytest fixtures for the Family Assistant test suite.

Tests run against a separate Postgres database (`family_assistant_test`) so
they exercise real SQL / SQLAlchemy / pgvector behavior. Each test runs in
a transaction wrapped in a SAVEPOINT so commits inside the request handler
stay isolated and get rolled back when the test finishes.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.auth.services import hash_password
from family_assistant.db import Base, get_session
from family_assistant.main import app
from family_assistant.settings import get_settings


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = make_url(get_settings().database_url).set(database="family_assistant_test")
    engine = create_engine(url, future=True)
    try:
        with engine.connect():
            pass
    except OperationalError as e:
        pytest.fail(
            f"Test database not reachable at {url}.\n"
            f"Create it with:\n"
            f"  docker compose exec postgres createdb -U family_assistant family_assistant_test\n"
            f"Underlying error: {e}"
        )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Per-test session wrapped in a transaction; commits become SAVEPOINTs and roll back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """TestClient that shares the test transaction via get_session override."""

    def _get_session_override() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = _get_session_override
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def user_password() -> str:
    return "correct-horse-battery-staple"


@pytest.fixture
def seeded_user(db_session: Session, user_password: str) -> User:
    user = User(email="alice@example.com", password_hash=hash_password(user_password))
    db_session.add(user)
    db_session.commit()
    return user
