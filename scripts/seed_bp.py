"""Seed a user's blood-pressure log from the 2024 export.

One-off import of ``Data/BP_Tracker_2024.csv`` into ``blood_pressure_readings``
for a single user. MAP is recomputed by the service layer (the CSV's MAP column
is ignored). Rows already present (matched on date + time + systolic + diastolic)
are skipped, so re-running is safe.

Pick the target user with an email argument; otherwise the first user in the DB
is used:

    docker compose exec -T app python scripts/seed_bp.py [user@example.com]
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from family_assistant.auth.models import User
from family_assistant.bp.models import BloodPressureReading
from family_assistant.bp.services import create_reading
from family_assistant.db import get_sessionmaker

CSV_PATH = Path(__file__).resolve().parent.parent / "Data" / "BP_Tracker_2024.csv"


def _resolve_user(db, email: str | None) -> User | None:
    if email:
        return db.scalar(select(User).where(User.email == email))
    return db.scalar(select(User).order_by(User.id.asc()))


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
        print(f"Seeding blood pressure readings for {user.email} (id={user.id})")

        with CSV_PATH.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                entry_date = datetime.strptime(row["Measurement Date"].strip(), "%B %d, %Y").date()
                time_raw = (row.get("Measurement Time") or "").strip()
                reading_time = datetime.strptime(time_raw, "%I:%M %p").time() if time_raw else None
                systolic = int(row["Systolic"])
                diastolic = int(row["Diastolic"])
                hr_raw = (row.get("Heart Rate") or "").strip()
                heart_rate = int(hr_raw) if hr_raw else None
                notes = (row.get("Notes") or "").strip() or None

                exists = db.scalar(
                    select(BloodPressureReading).where(
                        BloodPressureReading.user_id == user.id,
                        BloodPressureReading.date == entry_date,
                        BloodPressureReading.reading_time == reading_time,
                        BloodPressureReading.systolic == systolic,
                        BloodPressureReading.diastolic == diastolic,
                    )
                )
                if exists is not None:
                    skipped += 1
                    continue

                create_reading(
                    db,
                    user=user,
                    entry_date=entry_date,
                    reading_time=reading_time,
                    systolic=systolic,
                    diastolic=diastolic,
                    heart_rate=heart_rate,
                    notes=notes,
                )
                created += 1

    print(f"\nDone: {created} created, {skipped} skipped.")


if __name__ == "__main__":
    main()
