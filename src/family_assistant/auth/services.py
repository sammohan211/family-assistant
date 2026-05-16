"""Auth services: password hashing, sessions, seeding (PRD Sections 10.1, 15.1)."""

import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from family_assistant.auth.models import User, UserSession
from family_assistant.settings import get_settings

SESSION_DURATION = timedelta(days=30)
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def authenticate(db: DbSession, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_session(db: DbSession, user: User) -> UserSession:
    session = UserSession(
        token=secrets.token_urlsafe(32),
        csrf_token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + SESSION_DURATION,
    )
    db.add(session)
    db.commit()
    return session


def get_session_user(db: DbSession, token: str) -> User | None:
    session = db.get(UserSession, token)
    if session is None:
        return None
    if session.expires_at <= datetime.now(UTC):
        db.delete(session)
        db.commit()
        return None
    return session.user


def delete_session(db: DbSession, token: str) -> None:
    session = db.get(UserSession, token)
    if session is not None:
        db.delete(session)
        db.commit()


def seed_users(db: DbSession) -> None:
    """Idempotent: ensure the two pre-seeded users from env exist with current password hashes."""
    settings = get_settings()
    triples = [
        (settings.user1_email, settings.user1_password_hash, settings.user1_name),
        (settings.user2_email, settings.user2_password_hash, settings.user2_name),
    ]
    for email, password_hash, name in triples:
        if not email or not password_hash:
            continue
        resolved_name = name or email.split("@", 1)[0]
        existing = db.scalar(select(User).where(User.email == email))
        if existing is None:
            db.add(User(name=resolved_name, email=email, password_hash=password_hash))
        else:
            if existing.password_hash != password_hash:
                existing.password_hash = password_hash
            if name and existing.name != name:
                existing.name = name
    db.commit()
