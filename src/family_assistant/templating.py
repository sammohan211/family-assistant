"""Shared Jinja2Templates instance pointing at src/family_assistant/templates/."""

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup, escape

from family_assistant.settings import get_settings

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@pass_context
def csrf_input(context) -> Markup:
    """Render a hidden `_csrf` field bound to the current session, for HTML forms."""
    request = context.get("request")
    token = getattr(request.state, "csrf_token", "") if request is not None else ""
    if not token:
        return Markup("")
    return Markup(f'<input type="hidden" name="_csrf" value="{escape(token)}">')


@pass_context
def is_glucose_owner(context) -> bool:
    """True when the current session belongs to the Blood Sugar module's sole owner.

    UX only, for hiding the nav entry — the real gate is
    glucose/router.py::require_owner, which 404s independently of this.
    """
    request = context.get("request")
    email = getattr(request.state, "user_email", None) if request is not None else None
    owner_email = get_settings().user1_email
    return bool(email) and bool(owner_email) and email == owner_email


def local(value: datetime) -> datetime:
    """Show a DB timestamp in the app's local time (the container's ``TZ``).

    Postgres returns ``timestamptz`` values in UTC; formatting them directly
    showed times 4-5 hours off. Naive values are assumed local already.
    """
    return value.astimezone() if value.tzinfo is not None else value


templates.env.globals["csrf_input"] = csrf_input
templates.env.filters["local"] = local
templates.env.globals["is_glucose_owner"] = is_glucose_owner
