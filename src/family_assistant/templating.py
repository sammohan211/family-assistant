"""Shared Jinja2Templates instance pointing at src/family_assistant/templates/."""

from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup, escape

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


templates.env.globals["csrf_input"] = csrf_input
