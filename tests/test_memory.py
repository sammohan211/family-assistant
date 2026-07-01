"""Memory module integration tests (PRD Section 11.7)."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.auth.models import User
from family_assistant.family_member.models import FamilyMember
from family_assistant.memory.models import Memory


def _other_user(db_session: Session) -> User:
    from family_assistant.auth.services import hash_password

    user = User(name="Bob", email="bob@example.com", password_hash=hash_password("doesnt-matter"))
    db_session.add(user)
    db_session.commit()
    return user


def test_memory_requires_auth(client: TestClient) -> None:
    response = client.get("/memory", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_memory_list_renders_for_authenticated_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.get("/memory")
    assert response.status_code == 200
    assert b"Memory" in response.content
    assert b"No memories match" in response.content


def test_create_household_memory(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "household",
            "memory_type": "routine",
            "content": "We usually shop Sunday morning.",
            "tags": "shopping, weekend",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    memory = db_session.scalars(select(Memory)).one()
    assert memory.subject_type == "household"
    assert memory.subject_id is None
    assert memory.memory_type == "routine"
    assert memory.content == "We usually shop Sunday morning."
    assert memory.tags == ["shopping", "weekend"]
    assert memory.is_hard_restriction is False
    assert memory.source == "user"
    assert memory.created_by_user_id == seeded_user.id


def test_create_family_member_memory_with_hard_restriction(
    authenticated_client: TestClient, db_session: Session
) -> None:
    member = FamilyMember(name="Maya", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "family_member",
            "family_member_subject_id": str(member.id),
            "memory_type": "restriction",
            "content": "Severe peanut allergy.",
            "is_hard_restriction": "true",
            "tags": "allergy",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    memory = db_session.scalars(select(Memory)).one()
    assert memory.subject_type == "family_member"
    assert memory.subject_id == member.id
    assert memory.is_hard_restriction is True
    assert memory.tags == ["allergy"]


def test_create_user_memory(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "user",
            "user_subject_id": str(seeded_user.id),
            "memory_type": "preference",
            "content": "Prefers black coffee.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    memory = db_session.scalars(select(Memory)).one()
    assert memory.subject_type == "user"
    assert memory.subject_id == seeded_user.id


def test_create_requires_content(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "household",
            "memory_type": "preference",
            "content": "   ",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Content is required" in response.content


def test_create_rejects_invalid_memory_type(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "household",
            "memory_type": "not-a-real-type",
            "content": "something",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Choose a memory type" in response.content


def test_create_requires_family_member_when_subject_is_family_member(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "family_member",
            "memory_type": "preference",
            "content": "something",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Choose a family member" in response.content


def test_create_rejects_unknown_family_member(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "family_member",
            "family_member_subject_id": "99999",
            "memory_type": "preference",
            "content": "something",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Unknown family member" in response.content


def test_create_requires_user_when_subject_is_user(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/memory",
        data={
            "subject_type": "user",
            "memory_type": "preference",
            "content": "something",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Choose a user" in response.content


def test_update_missing_memory_redirects_without_writing(
    authenticated_client: TestClient, db_session: Session
) -> None:
    # Regression: POST to a deleted/non-existent ID used to call update_memory
    # (which returns None) and then redirect 303 as if the edit succeeded.
    response = authenticated_client.post(
        "/memory/99999",
        data={
            "subject_type": "household",
            "memory_type": "routine",
            "content": "Ghost routine",
            "tags": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/memory"
    assert db_session.scalars(select(Memory)).all() == []


def test_update_memory_changes_subject_and_clears_subject_id_for_household(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=["monday"])
    db_session.add(member)
    db_session.commit()
    memory = Memory(
        subject_type="family_member",
        subject_id=member.id,
        memory_type="preference",
        content="Likes oranges.",
        is_hard_restriction=False,
        source="user",
        tags=["fruit"],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()

    response = authenticated_client.post(
        f"/memory/{memory.id}",
        data={
            "subject_type": "household",
            "memory_type": "routine",
            "content": "We tend to skip dessert on weekdays.",
            "tags": "diet",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(memory)
    assert memory.subject_type == "household"
    assert memory.subject_id is None
    assert memory.memory_type == "routine"
    assert memory.tags == ["diet"]


def test_delete_memory(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        subject_id=None,
        memory_type="preference",
        content="Soft preference.",
        is_hard_restriction=False,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()
    memory_id = memory.id

    response = authenticated_client.post(f"/memory/{memory_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(Memory, memory_id) is None


def test_list_filters_by_memory_type(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    db_session.add_all(
        [
            Memory(
                subject_type="household",
                memory_type="preference",
                content="A soft preference",
                is_hard_restriction=False,
                source="user",
                tags=[],
                created_by_user_id=seeded_user.id,
            ),
            Memory(
                subject_type="household",
                memory_type="routine",
                content="A weekly routine",
                is_hard_restriction=False,
                source="user",
                tags=[],
                created_by_user_id=seeded_user.id,
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/memory?memory_type=routine")
    assert response.status_code == 200
    assert b"A weekly routine" in response.content
    assert b"A soft preference" not in response.content


def test_list_filters_by_keyword(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    db_session.add_all(
        [
            Memory(
                subject_type="household",
                memory_type="preference",
                content="Likes one-pot meals on weekdays",
                is_hard_restriction=False,
                source="user",
                tags=[],
                created_by_user_id=seeded_user.id,
            ),
            Memory(
                subject_type="household",
                memory_type="preference",
                content="Prefers slow-cooked stews",
                is_hard_restriction=False,
                source="user",
                tags=[],
                created_by_user_id=seeded_user.id,
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/memory?q=one-pot")
    assert response.status_code == 200
    assert b"one-pot" in response.content
    assert b"slow-cooked" not in response.content


def test_list_filters_by_tag(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    db_session.add_all(
        [
            Memory(
                subject_type="household",
                memory_type="preference",
                content="Tagged memory",
                is_hard_restriction=False,
                source="user",
                tags=["weekday"],
                created_by_user_id=seeded_user.id,
            ),
            Memory(
                subject_type="household",
                memory_type="preference",
                content="Untagged memory",
                is_hard_restriction=False,
                source="user",
                tags=[],
                created_by_user_id=seeded_user.id,
            ),
        ]
    )
    db_session.commit()

    response = authenticated_client.get("/memory?tag=weekday")
    assert response.status_code == 200
    assert b"Tagged memory" in response.content
    assert b"Untagged memory" not in response.content


def test_delete_hard_restriction_requires_confirmation(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        memory_type="restriction",
        content="No raw shellfish",
        is_hard_restriction=True,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()
    memory_id = memory.id

    response = authenticated_client.post(f"/memory/{memory_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/memory/{memory_id}/delete"
    db_session.expire_all()
    assert db_session.get(Memory, memory_id) is not None


def test_delete_hard_restriction_with_confirm_succeeds(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        memory_type="restriction",
        content="No raw shellfish",
        is_hard_restriction=True,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()
    memory_id = memory.id

    response = authenticated_client.post(
        f"/memory/{memory_id}/delete", data={"confirm": "yes"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/memory"
    db_session.expire_all()
    assert db_session.get(Memory, memory_id) is None


def test_delete_confirm_page_renders(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        memory_type="restriction",
        content="Peanut allergy across household",
        is_hard_restriction=True,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()

    response = authenticated_client.get(f"/memory/{memory.id}/delete")
    assert response.status_code == 200
    assert b"Peanut allergy across household" in response.content
    assert b"Yes, delete this memory" in response.content


def test_update_hard_restriction_requires_confirmation(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        memory_type="restriction",
        content="Peanut allergy",
        is_hard_restriction=True,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()

    response = authenticated_client.post(
        f"/memory/{memory.id}",
        data={
            "subject_type": "household",
            "memory_type": "restriction",
            "content": "Tree-nut allergy too",
            "is_hard_restriction": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"confirmation" in response.content.lower()
    db_session.refresh(memory)
    assert memory.content == "Peanut allergy"


def test_update_hard_restriction_with_confirm_succeeds(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    memory = Memory(
        subject_type="household",
        memory_type="restriction",
        content="Peanut allergy",
        is_hard_restriction=True,
        source="user",
        tags=[],
        created_by_user_id=seeded_user.id,
    )
    db_session.add(memory)
    db_session.commit()

    response = authenticated_client.post(
        f"/memory/{memory.id}",
        data={
            "subject_type": "household",
            "memory_type": "restriction",
            "content": "Tree-nut allergy too",
            "is_hard_restriction": "true",
            "confirm_hard_restriction": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(memory)
    assert memory.content == "Tree-nut allergy too"


def test_hard_restriction_renders_badge(
    authenticated_client: TestClient, db_session: Session, seeded_user: User
) -> None:
    db_session.add(
        Memory(
            subject_type="household",
            memory_type="restriction",
            content="No raw shellfish in the house",
            is_hard_restriction=True,
            source="user",
            tags=["allergy"],
            created_by_user_id=seeded_user.id,
        )
    )
    db_session.commit()

    response = authenticated_client.get("/memory")
    assert response.status_code == 200
    assert b"Hard restriction" in response.content
