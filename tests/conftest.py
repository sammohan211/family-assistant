"""Pytest fixtures for the Family Assistant test suite.

Tests run against a separate Postgres database (`family_assistant_test`) so
they exercise real SQL / SQLAlchemy / pgvector behavior. Each test runs in
a transaction wrapped in a SAVEPOINT so commits inside the request handler
stay isolated and get rolled back when the test finishes.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from family_assistant.auth.models import User, UserSession
from family_assistant.auth.services import hash_password
from family_assistant.db import get_session
from family_assistant.main import app

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.fail(
            "DATABASE_URL is not set. Tests need a Postgres URL so they can "
            "swap in the family_assistant_test database. Populate `.env` "
            "(see SETUP.md §4) or export DATABASE_URL before running pytest."
        )
    url = make_url(database_url).set(database="family_assistant_test")
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.commit()
    except OperationalError as e:
        pytest.fail(
            f"Test database not reachable at {url}.\n"
            f"Create it with:\n"
            f"  docker compose exec postgres createdb -U family_assistant family_assistant_test\n"
            f"Underlying error: {e}"
        )
    command.upgrade(_alembic_config(str(url)), "head")
    yield engine
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
    user = User(name="Alice", email="alice@example.com", password_hash=hash_password(user_password))
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def authenticated_client(
    client: TestClient, seeded_user: User, user_password: str, db_session: Session
) -> TestClient:
    """TestClient logged in as seeded_user. POSTs auto-include the session's CSRF token."""
    client.post(
        "/auth/login",
        data={"email": seeded_user.email, "password": user_password},
        follow_redirects=False,
    )
    session_row = db_session.scalar(
        select(UserSession).where(UserSession.user_id == seeded_user.id)
    )
    assert session_row is not None
    csrf_token = session_row.csrf_token
    client.csrf_token = csrf_token  # type: ignore[attr-defined]

    original_post = client.post

    def post_with_csrf(url, *args, data=None, **kwargs):
        merged = dict(data or {})
        merged.setdefault("_csrf", csrf_token)
        return original_post(url, *args, data=merged, **kwargs)

    client.post = post_with_csrf  # type: ignore[method-assign]
    return client
