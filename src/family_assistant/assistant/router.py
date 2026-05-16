"""Assistant input router (PRD Section 14.3 / 11)."""

from fastapi import APIRouter

router = APIRouter(prefix="/assistant", tags=["assistant"])
