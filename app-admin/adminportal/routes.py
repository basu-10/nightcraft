"""Admin handoff routes."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Blueprint, current_app, g, render_template
from flask import redirect

main_bp = Blueprint("main", __name__)


def build_auth_handoff_url(auth_url: str, return_path: str, return_param: str = "next") -> str:
    """Build a login URL that returns the user to a specific path after auth."""
    parts = urlsplit(auth_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[return_param] = return_path
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@main_bp.get("/")
def admin_handoff():
    auth_handoff_url = build_auth_handoff_url(
        current_app.config["AUTH_URL"],
        current_app.config["ADMIN_RETURN_PATH"],
        current_app.config["AUTH_RETURN_PARAM"],
    )
    return render_template(
        "login_handoff.html",
        auth_handoff_url=auth_handoff_url,
        shared_user=g.get("shared_user"),
        is_admin=g.get("is_admin", False),
    )


@main_bp.get("/login")
def login_redirect():
    return redirect(
        build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            current_app.config["ADMIN_RETURN_PATH"],
            current_app.config["AUTH_RETURN_PARAM"],
        )
    )


@main_bp.get("/healthz")
def healthz():
    return {"status": "ok", "service": "admin-handoff"}, 200
