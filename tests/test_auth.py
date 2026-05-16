"""Auth module integration tests."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.auth.dependencies import SESSION_COOKIE_NAME
from family_assistant.auth.models import User, UserSession


def test_login_page_renders(client: TestClient) -> None:
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert b"Sign in" in response.content


def test_login_unknown_email_returns_401(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        data={"email": "nobody@example.com", "password": "anything"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert b"Invalid email or password" in response.content
    assert SESSION_COOKIE_NAME not in response.cookies


def test_login_wrong_password_returns_401(client: TestClient, seeded_user: User) -> None:
    response = client.post(
        "/auth/login",
        data={"email": seeded_user.email, "password": "wrong-password"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


def test_login_correct_credentials_redirects_and_sets_cookie(
    client: TestClient, seeded_user: User, user_password: str
) -> None:
    response = client.post(
        "/auth/login",
        data={"email": seeded_user.email, "password": user_password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert SESSION_COOKIE_NAME in response.cookies


def test_login_creates_session_row(
    client: TestClient, seeded_user: User, user_password: str, db_session: Session
) -> None:
    client.post(
        "/auth/login",
        data={"email": seeded_user.email, "password": user_password},
        follow_redirects=False,
    )
    sessions = db_session.scalars(
        select(UserSession).where(UserSession.user_id == seeded_user.id)
    ).all()
    assert len(sessions) == 1


def test_logout_deletes_session_and_clears_cookie(
    client: TestClient, seeded_user: User, user_password: str, db_session: Session
) -> None:
    client.post(
        "/auth/login",
        data={"email": seeded_user.email, "password": user_password},
    )
    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"
    sessions = db_session.scalars(
        select(UserSession).where(UserSession.user_id == seeded_user.id)
    ).all()
    assert len(sessions) == 0
