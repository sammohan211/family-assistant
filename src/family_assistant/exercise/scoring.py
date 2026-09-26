"""Work-score calculator for exercise logs (PRD Section 10.7).

Pure functions — no DB, no IO. Called by the service layer at write time
and persisted on the ``exercise_logs.work_score`` column so historical
scores stay stable when a user later changes their body weight.

A work score is only meaningful against earlier logs of the *same* exercise
(PRD §10.16) — the scoring types produce incomparable numbers.
"""

from decimal import Decimal

SCORING_TYPES: tuple[str, ...] = ("weighted", "distance", "bodyweight_fraction", "timed")


class ScoringInputError(ValueError):
    """Raised when the inputs needed for a given scoring_type are missing."""


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def compute_work_score(
    scoring_type: str,
    *,
    body_weight: Decimal | None,
    bodyweight_fraction: Decimal | None,
    sets: int | None,
    reps: int | None,
    weight: Decimal | None,
    distance_km: Decimal | None,
    duration_minutes: int | None = None,
) -> Decimal:
    """Return the work score for one log entry.

    Formulas (PRD §10.7, §10.16):
      - weighted:            weight * reps * sets
      - distance:            distance_km * body_weight
      - bodyweight_fraction: body_weight * bodyweight_fraction * reps * sets
      - timed:               duration_minutes
    """
    if scoring_type == "weighted":
        if weight is None or reps is None or sets is None:
            raise ScoringInputError("weighted scoring requires weight, reps, and sets")
        return _to_decimal(weight) * _to_decimal(reps) * _to_decimal(sets)

    if scoring_type == "distance":
        if distance_km is None:
            raise ScoringInputError("distance scoring requires distance_km")
        if body_weight is None:
            raise ScoringInputError("distance scoring requires the user's body_weight to be set")
        return _to_decimal(distance_km) * _to_decimal(body_weight)

    if scoring_type == "bodyweight_fraction":
        if reps is None or sets is None:
            raise ScoringInputError("bodyweight_fraction scoring requires reps and sets")
        if body_weight is None:
            raise ScoringInputError(
                "bodyweight_fraction scoring requires the user's body_weight to be set"
            )
        fraction = (
            _to_decimal(bodyweight_fraction)
            if bodyweight_fraction is not None
            else Decimal("1.000")
        )
        return _to_decimal(body_weight) * fraction * _to_decimal(reps) * _to_decimal(sets)

    if scoring_type == "timed":
        if duration_minutes is None:
            raise ScoringInputError("timed scoring requires duration_minutes")
        return _to_decimal(duration_minutes)

    raise ScoringInputError(f"Unknown scoring_type: {scoring_type!r}")
