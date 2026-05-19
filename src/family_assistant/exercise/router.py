"""Exercise router (PRD Section 10.7).

The full UI (catalog, log entry, weekly view) lands in follow-up commits.
This stub keeps ``/exercise`` reachable so the nav link doesn't 404 while
the redesigned UI is under construction.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from family_assistant.auth.dependencies import require_user
from family_assistant.templating import templates

router = APIRouter(
    prefix="/exercise",
    tags=["exercise"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_class=HTMLResponse)
def placeholder(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "exercise/placeholder.html", {"request": request})
