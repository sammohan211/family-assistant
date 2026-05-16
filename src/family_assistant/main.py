"""Bootstrap FastAPI app so the Docker stack runs end-to-end before modules land."""

from fastapi import FastAPI

from family_assistant.assistant import router as assistant_router
from family_assistant.auth import router as auth_router
from family_assistant.dashboard import router as dashboard_router
from family_assistant.exercise import router as exercise_router
from family_assistant.family_member import router as family_member_router
from family_assistant.grocery import router as grocery_router
from family_assistant.lunch_plan import router as lunch_plan_router
from family_assistant.meal_plan import router as meal_plan_router
from family_assistant.memory import router as memory_router

app = FastAPI(title="Family Assistant")

app.include_router(auth_router)
app.include_router(family_member_router)
app.include_router(grocery_router)
app.include_router(meal_plan_router)
app.include_router(lunch_plan_router)
app.include_router(exercise_router)
app.include_router(memory_router)
app.include_router(assistant_router)
app.include_router(dashboard_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"app": "Family Assistant", "status": "bootstrap"}
