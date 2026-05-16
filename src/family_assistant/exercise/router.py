"""Exercise router (PRD Section 10.7)."""

from fastapi import APIRouter

router = APIRouter(prefix="/exercise", tags=["exercise"])
