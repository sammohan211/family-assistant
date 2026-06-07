"""Seed a user's hike log from the 2024 Bruce Trail export.

One-off import of ``Data/Bruce_Trail_Hikes_2024.csv`` into ``hikes`` for a
single user. ``speed_kmh`` is recomputed by the service layer (the CSV's Speed
column is ignored). Rows already present (matched on date + segment name) are
skipped, so re-running is safe.

Pick the target user with an email argument; otherwise the first user in the
DB is used:

    docker compose exec -T app python scripts/seed_hikes.py [user@example.com]
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from family_assistant.auth.models import User
from family_assistant.db import get_sessionmaker
from family_assistant.hike.models import Hike
from family_assistant.hike.services import create_hike

CSV_PATH = Path(__file__).resolve().parent.parent / "Data" / "Bruce_Trail_Hikes_2024.csv"


def _resolve_user(db, email: str | None) -> User | None:
    if email:
        return db.scalar(select(User).where(User.email == email))
    return db.scalar(select(User).order_by(User.id.asc()))


def _parse_time(raw: str):
    raw = (raw or "").strip()
    return datetime.strptime(raw, "%I:%M %p").time() if raw else None


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else None
    if not CSV_PATH.exists():
        print(f"CSV not found at {CSV_PATH}")
        sys.exit(1)

    created = 0
    skipped = 0
    with get_sessionmaker()() as db:
        user = _resolve_user(db, email)
        if user is None:
            print("No matching user found. Pass an email that exists in the DB.")
            sys.exit(1)
        print(f"Seeding hikes for {user.email} (id={user.id})")

        with CSV_PATH.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                entry_date = datetime.strptime(row["Date"].strip(), "%B %d, %Y").date()
                name = row["Hike Name"].strip()

                exists = db.scalar(
                    select(Hike).where(
                        Hike.user_id == user.id,
                        Hike.date == entry_date,
                        Hike.name == name,
                    )
                )
                if exists is not None:
                    skipped += 1
                    continue

                create_hike(
                    db,
                    user=user,
                    entry_date=entry_date,
                    section=row["Section"].strip(),
                    name=name,
                    start_location=(row.get("Start Location") or "").strip() or None,
                    start_time=_parse_time(row.get("Start Time", "")),
                    end_location=(row.get("End Location") or "").strip() or None,
                    end_time=_parse_time(row.get("End Time", "")),
                    distance_km=Decimal(row["Total Distance (KMs)"].strip()),
                    duration_minutes=int(row["Total Duration (Mins)"]),
                    notes=None,
                )
                created += 1

    print(f"\nDone: {created} created, {skipped} skipped.")


if __name__ == "__main__":
    main()
