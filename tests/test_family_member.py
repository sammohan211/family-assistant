"""FamilyMember module integration tests."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from family_assistant.family_member.models import FamilyMember


def test_list_requires_auth(client: TestClient) -> None:
    response = client.get("/family", follow_redirects=False)
    assert response.status_code == 401


def test_list_renders_empty_for_authenticated_user(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.get("/family")
    assert response.status_code == 200
    assert b"Family" in response.content
    assert b"No family members yet" in response.content


def test_create_family_member(authenticated_client: TestClient, db_session: Session) -> None:
    response = authenticated_client.post(
        "/family",
        data={
            "name": "Lila",
            "notes": "Likes mango",
            "school_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/family"
    members = db_session.scalars(select(FamilyMember)).all()
    assert len(members) == 1
    assert members[0].name == "Lila"
    assert members[0].notes == "Likes mango"
    assert members[0].school_days == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]


def test_create_requires_name(authenticated_client: TestClient) -> None:
    response = authenticated_client.post(
        "/family",
        data={"name": "  ", "notes": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert b"Name is required" in response.content


def test_create_ignores_unknown_school_days(
    authenticated_client: TestClient, db_session: Session
) -> None:
    authenticated_client.post(
        "/family",
        data={"name": "Lila", "school_days": ["monday", "funday", "tuesday"]},
        follow_redirects=False,
    )
    member = db_session.scalars(select(FamilyMember)).one()
    assert member.school_days == ["monday", "tuesday"]


def test_update_family_member(authenticated_client: TestClient, db_session: Session) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=[])
    db_session.add(member)
    db_session.commit()

    response = authenticated_client.post(
        f"/family/{member.id}",
        data={"name": "Lila S.", "notes": "Likes mango", "school_days": ["monday"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db_session.refresh(member)
    assert member.name == "Lila S."
    assert member.notes == "Likes mango"
    assert member.school_days == ["monday"]


def test_delete_family_member(authenticated_client: TestClient, db_session: Session) -> None:
    member = FamilyMember(name="Lila", notes=None, school_days=[])
    db_session.add(member)
    db_session.commit()
    member_id = member.id

    response = authenticated_client.post(
        f"/family/{member_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db_session.get(FamilyMember, member_id) is None
