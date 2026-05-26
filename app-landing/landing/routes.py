"""Landing routes."""
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib import request as urllib_request
from urllib.error import URLError

from flask import Blueprint, current_app, render_template, request
from flask import redirect

main_bp = Blueprint("main", __name__)


def build_auth_handoff_url(auth_url: str, return_path: str, return_param: str = "next") -> str:
    """Build a login URL that returns the user to a specific path after auth."""
    parts = urlsplit(auth_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[return_param] = return_path
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _session_me_url() -> str:
    configured = (current_app.config.get("AUTH_SESSION_ME_URL", "") or "").strip()
    if not configured:
        return ""
    if configured.startswith("http://") or configured.startswith("https://"):
        return configured
    return f"{request.host_url.rstrip('/')}/{configured.lstrip('/')}"


def _fetch_shared_auth_user():
    if current_app.testing:
        return None

    endpoint = _session_me_url()
    if not endpoint:
        return None

    req = urllib_request.Request(
        endpoint,
        method="GET",
        headers={
            "Accept": "application/json",
            "Cookie": request.headers.get("Cookie", ""),
            "X-Forwarded-Prefix": request.headers.get("X-Forwarded-Prefix", ""),
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, ValueError, OSError):
        return None

    if not isinstance(payload, dict) or not payload.get("authenticated"):
        return None

    user = payload.get("user") or {}
    if not isinstance(user, dict):
        return None

    username = (user.get("preferred_username") or "").strip()
    if not username:
        username = (user.get("email") or "").split("@", 1)[0].strip()
    if not username:
        username = "User"

    roles = user.get("roles")
    if isinstance(roles, str):
        normalized_roles = {roles.strip().lower()}
    elif isinstance(roles, (list, tuple, set)):
        normalized_roles = {str(role).strip().lower() for role in roles}
    else:
        normalized_roles = set()

    return {
        "username": username,
        "is_admin": "admin" in normalized_roles or bool(user.get("is_admin", False)),
    }


def _admin_target(base_url: str) -> str:
    candidate = (base_url or "").strip()
    if not candidate:
        return "/admin"
    return f"{candidate.rstrip('/')}/admin"


def _central_admin_url() -> str:
    """Return the central admin hub path, normalizing legacy /admin config."""
    configured = (current_app.config.get("ADMIN_URL", "") or "").strip()
    if not configured or configured == "/admin":
        return "/platform-admin"
    return configured


@main_bp.get("/")
def home():
    shared_user = _fetch_shared_auth_user()
    home_path = "/"

    cards = [
        {
            "name": "DevRadio",
            "tagline": "Automated radio for technical reading.",
            "description": "RSS ingestion, content scraping, queueing, and topic-based listening channels.",
            "url": current_app.config["DEVRADIO_URL"],
            "status": "Active",
            "stack": "Python, RSS, TTS, Queue",
        },
        {
            "name": "SeekSage",
            "tagline": "Research agents with real tools.",
            "description": "React-based agent system with local/online model providers, search, wiki lookup, slide generation, and tool workflows.",
            "url": f"{current_app.config['SEEKSAGE_URL'].rstrip('/')}/ui",
            "status": "Active",
            "stack": "Python, FastAPI, React",
        },
        {
            "name": "Curio",
            "tagline": "Cultural discovery for books, songs, art, people, and ideas.",
            "description": "Lists, notes, posts, item pages, and discussions that connect culture across formats.",
            "url": current_app.config["CURIO_URL"],
            "status": "In Development",
            "stack": "Next.js, Prisma, PostgreSQL",
        },
        {
            "name": "NoteStack",
            "tagline": "Offline-first notes that stay yours.",
            "description": "Cross-platform notes with offline-first storage, end-to-end sync, and data portability.",
            "url": f"{current_app.config['NOTESTACK_URL'].rstrip('/')}/app",
            "status": "Active",
            "stack": "Python, Flask, PostgreSQL",
        },
    ]

    admin_url = _central_admin_url()

    return render_template(
        "home.html",
        cards=cards,
        shared_user=shared_user,
        auth_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        register_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"].replace("/login", "/register"),
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        auth_admin_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            admin_url,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        admin_url=admin_url,
    )


@main_bp.get("/platform-admin")
@main_bp.get("/admin")
def admin_dashboard():
    shared_user = _fetch_shared_auth_user()
    home_path = "/"
    admin_url = _central_admin_url()

    admin_cards = [
        {
            "name": "DevRadio Admin",
            "description": "Manage channels, curation, and automation settings.",
            "url": _admin_target(current_app.config["DEVRADIO_URL"]),
            "status": "Live",
        },
        {
            "name": "Curio Admin",
            "description": "Review catalog data and product-level administration.",
            "url": _admin_target(current_app.config["CURIO_URL"]),
            "status": "Live",
        },
        {
            "name": "SeekSage Admin",
            "description": "Manage users, activity logs, and workspace-level operations.",
            "url": _admin_target(current_app.config["SEEKSAGE_URL"]),
            "status": "Live",
        },
        {
            "name": "NoteStack Admin",
            "description": "Manage note users, roles, and account operations.",
            "url": _admin_target(current_app.config["NOTESTACK_URL"]),
            "status": "Live",
        },
        {
            "name": "Game Hub",
            "description": "Open game operations and service-level controls.",
            "url": current_app.config["GAME_URL"],
            "status": "Live",
        },
    ]

    return render_template(
        "admin.html",
        shared_user=shared_user,
        is_admin=bool(shared_user and shared_user.get("is_admin")),
        cards=admin_cards,
        auth_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        auth_admin_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            admin_url,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        home_url=home_path,
    )


@main_bp.get("/login")
def login_redirect():
    return redirect(
        build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            "/",
            current_app.config["AUTH_RETURN_PARAM"],
        )
    )


@main_bp.get("/dev-profile")
def dev_profile():
    shared_user = _fetch_shared_auth_user()
    return render_template(
        "dev_profile.html",
        shared_user=shared_user,
        auth_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            "/dev-profile",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            "/dev-profile",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
    )


@main_bp.get("/about")
def about():
    shared_user = _fetch_shared_auth_user()
    return render_template(
        "about.html",
        shared_user=shared_user,
        auth_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            "/about",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            "/about",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
    )


@main_bp.get("/next-updates")
def next_updates():
    shared_user = _fetch_shared_auth_user()
    return render_template(
        "next_updates.html",
        shared_user=shared_user,
        auth_url=build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            "/next-updates",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            "/next-updates",
            current_app.config["AUTH_RETURN_PARAM"],
        ),
    )


@main_bp.get("/healthz")
def healthz():
    return {"status": "ok", "service": "landing"}, 200
