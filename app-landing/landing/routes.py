"""Landing routes."""
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

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


def _auth_admin_url(path: str) -> str:
    """Build a URL to an auth-service admin endpoint."""
    configured = (current_app.config.get("AUTH_ADMIN_BASE_URL", "/auth") or "/auth").strip()
    if configured.startswith("http://") or configured.startswith("https://"):
        return f"{configured.rstrip('/')}{path}"
    return f"{request.host_url.rstrip('/')}/{configured.lstrip('/')}{path}"


def _call_auth_admin(method: str, path: str, *, params=None, json_body=None):
    """Call an auth-service admin endpoint, forwarding the browser session cookie.

    Returns a ``(status, payload)`` tuple. On transport failure ``status`` is
    ``None`` and ``payload`` is an error dict.
    """
    if current_app.testing:
        return None, {"error": "auth_service_unavailable", "error_description": "Auth service unavailable in testing"}

    url = _auth_admin_url(path)
    if params:
        url = f"{url}?{urlencode(params)}"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": request.headers.get("Cookie", ""),
        "X-Forwarded-Prefix": request.headers.get("X-Forwarded-Prefix", ""),
    }
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None

    req = urllib_request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib_request.urlopen(req, timeout=2.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            return exc.code, {"error": "auth_service_error", "error_description": "Auth service returned an error"}
    except (URLError, ValueError, OSError):
        return None, {"error": "auth_service_unreachable", "error_description": "Could not reach the auth service"}


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
            "name": "NoteStack",
            "tagline": "Offline-first notes that stay yours.",
            "description": "Cross-platform notes with offline-first storage, end-to-end sync, and data portability.",
            "url": f"{current_app.config['NOTESTACK_URL'].rstrip('/')}/app",
            "status": "Active",
            "stack": "Python, Flask, PostgreSQL",
        },
        {
            "name": "DevRadio",
            "tagline": "Automated radio for technical reading.",
            "description": "RSS ingestion, content scraping, queueing, and topic-based listening channels.",
            "url": current_app.config["DEVRADIO_URL"],
            "status": "Active",
            "stack": "Python, RSS, TTS, Queue",
        },
        {
            "name": "Alfred",
            "tagline": "Your local AI-powered planner that orchestrates tools across your Library, Web, and Editor.",
            "description": "Plan, orchestrate, and get things done with an intelligent workspace that helps you focus on outcomes, not context switching.",
            "url": current_app.config["ALFRED_URL"],
            "status": "Active",
            "stack": "Python, LLM, RAG",
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


@main_bp.get("/alfred")
def alfred_home():
    return redirect(current_app.config["ALFRED_URL"])


@main_bp.get("/texttrace")
def texttrace_home():
    return render_template(
        "texttrace.html",
        texttrace_url=current_app.config["TEXTTRACE_URL"],
        texttrace_github_url=current_app.config["TEXTTRACE_GITHUB_URL"] or current_app.config["TEXTTRACE_URL"],
        texttrace_download_url=current_app.config["TEXTTRACE_DOWNLOAD_URL"] or current_app.config["TEXTTRACE_URL"],
    )


@main_bp.get("/scratchpad")
def scratchpad_landing():
    return render_template("mindmap-landing.html")


@main_bp.get("/scratchpad/app")
def scratchpad_app():
    return render_template("mindmap-app.html")


@main_bp.get("/miobook")
def notebook_landing():
    return render_template("browser-notebook-app-landing.html")


@main_bp.get("/miobook/app")
def notebook_app():
    return render_template("browser-notebook-app.html")


@main_bp.get("/quickpost")
def quickpost_landing():
    return render_template("quickposts-landing.html")


@main_bp.get("/quickpost/quickcollages")
def quickpost_quickcollages():
    return render_template("quickposts-app-quickcollages.html")


@main_bp.get("/quickpost/quickedits")
def quickpost_quickedits():
    return render_template("quickposts-app-quickedits.html")


@main_bp.get("/quickpost/quickslides")
def quickpost_quickslides():
    return render_template("quickposts-app-quickslides.html")


@main_bp.get("/experimental")
def experimental_apps():
    shared_user = _fetch_shared_auth_user()
    home_path = "/"

    experimental_sections = [
        {
            "heading": "Sometimes life is better with a little less complexity and pretty interfaces lol...",
            "subheading": None,
            "apps": [
                {
                    "name": "TinyXL",
                    "tagline": "Tiny tools that do one thing well.",
                    "description": "A small collection of lightweight utilities built for speed and simplicity.",
                    "url": current_app.config["TINYXL_URL"],
                    "status": "Active",
                    "stack": "Python, Web",
                },
                {
                    "name": "TexTrace",
                    "tagline": "Locally running embedding model based search.",
                    "description": "A local-first semantic search app powered by an on-device embedding model. We simply link out to the releases and README pages.",
                    "url": current_app.config["TEXTTRACE_URL"],
                    "status": "Released",
                    "stack": "Python, Embeddings, Local",
                },
            ],
        },
        {
            "heading": "For the love of the Tech, People, Nature and more...",
            "subheading": "(proof of concept only / local accounts only)",
            "apps": [
                {
                    "name": "Lazy Games",
                    "tagline": "Small games to unwind, now open to everyone.",
                    "description": "A collection of casual games that were tucked away in the admin section, now playable by all.",
                    "url": current_app.config["GAME_URL"],
                    "status": "Active",
                    "stack": "JavaScript, Canvas",
                },
                {
                    "name": "The Green Pledge",
                    "tagline": "Small commitments for a healthier planet.",
                    "description": "A gentle way to track everyday promises to nature and community.",
                    "url": current_app.config["GREENPLEDGE_URL"],
                    "status": "Not Built",
                    "stack": "Planned",
                },
                {
                    "name": "ScratchPad",
                    "tagline": "Mind maps that grow with your ideas.",
                    "description": "A mindmap app for visually organizing thoughts, notes, and the connections between them.",
                    "url": current_app.config["SCRATCHPAD_URL"],
                    "status": "In Development",
                    "stack": "JavaScript, Canvas",
                },
                {
                    "name": "NoteFlow",
                    "tagline": "A Jupyter-notebook inspired text app.",
                    "description": "An interactive document app that mixes prose and runnable blocks for quick experiments.",
                    "url": current_app.config["NOTEBOOK_URL"],
                    "status": "In Development",
                    "stack": "Python, Web",
                },
            ],
            "subheading_apps": [
                {
                    "name": "FOSSil",
                    "tagline": "A free, open library that belongs to its readers.",
                    "description": "A peer-to-peer shelf where students and scholars publish and preserve their notes, essays, and ideas as public, portable writing.",
                    "url": current_app.config["FOSSIL_URL"],
                    "status": "In Development",
                    "stack": "P2P, Web, Decentralized",
                },
                {
                    "name": "Neera",
                    "tagline": "Cultural discovery for books, songs, art, people, and ideas.",
                    "description": "Lists, notes, posts, item pages, and discussions that connect culture across formats.",
                    "url": current_app.config["NEERA_URL"],
                    "status": "In Development",
                    "stack": "Next.js, Prisma, PostgreSQL",
                },
                {
                    "name": "QuickPost",
                    "tagline": "Text-to-post pipeline for quick sharing.",
                    "description": "Turn drafts into posts, slides, and edits with a lightweight local-first pipeline.",
                    "url": current_app.config["QUICKPOST_URL"],
                    "status": "In Development",
                    "stack": "Python, Web",
                },
            ],
        },
    ]

    return render_template(
        "experimental.html",
        sections=experimental_sections,
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
        logout_url=build_auth_handoff_url(
            current_app.config["LOGOUT_URL"],
            home_path,
            current_app.config["AUTH_RETURN_PARAM"],
        ),
        home_url=home_path,
        admin_url=_central_admin_url(),
    )


_FOSSIL_POSTS = [
    {
        "id": 1,
        "title": "On Keeping a Slow Notebook",
        "author": "M. Okonkwo",
        "date": "2026-03-18",
        "tags": ["practice", "notes"],
        "excerpt": "The point was never to capture everything. It was to give the mind a second place to think, slower than the first.",
    },
    {
        "id": 2,
        "title": "A Short Defense of Unfinished Essays",
        "author": "L. Vesely",
        "date": "2026-02-27",
        "tags": ["writing", "craft"],
        "excerpt": "An essay that ends with a question is not a failure. It is an invitation left open on a public shelf.",
    },
    {
        "id": 3,
        "title": "What My Students Taught Me About Citation",
        "author": "R. Banerjee",
        "date": "2026-01-09",
        "tags": ["teaching", "scholarship"],
        "excerpt": "Credit is a form of continuity. When we link a thought back to its source, we let ideas travel without losing their lineage.",
    },
    {
        "id": 4,
        "title": "Notes From a Train: Fragments on Attention",
        "author": "S. Adeyemi",
        "date": "2025-12-02",
        "tags": ["attention", "daily"],
        "excerpt": "The window became a page. The landscape scrolled, and for once I did not try to keep any of it except what stayed.",
    },
]


@main_bp.get("/fossil")
def fossil_library():
    fossil_user = session.get("fossil_user")
    return render_template(
        "fossil.html",
        posts=_FOSSIL_POSTS,
        user=fossil_user,
        fossil_url=current_app.config["FOSSIL_URL"],
    )


@main_bp.post("/fossil/login")
def fossil_login():
    username = (request.form.get("username") or "").strip()
    if username:
        session["fossil_user"] = username
    return redirect(current_app.config["FOSSIL_URL"])


@main_bp.post("/fossil/login-demo")
def fossil_login_demo():
    session["fossil_user"] = "demo-user-ALEX"
    return redirect(current_app.config["FOSSIL_URL"])


@main_bp.post("/fossil/logout")
def fossil_logout():
    session.pop("fossil_user", None)
    return redirect(current_app.config["FOSSIL_URL"])


@main_bp.post("/fossil/post")
def fossil_post():
    if not session.get("fossil_user"):
        return redirect(current_app.config["FOSSIL_URL"])

    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    if title and body:
        next_id = (max((post["id"] for post in _FOSSIL_POSTS), default=0)) + 1
        _FOSSIL_POSTS.insert(
            0,
            {
                "id": next_id,
                "title": title,
                "author": session["fossil_user"],
                "date": date.today().isoformat(),
                "tags": ["draft"],
                "excerpt": body[:180],
            },
        )
    return redirect(current_app.config["FOSSIL_URL"])


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
            "name": "Neera Admin",
            "description": "Review catalog data and product-level administration.",
            "url": _admin_target(current_app.config["NEERA_URL"]),
            "status": "Live",
        },
        {
            "name": "NoteStack Admin",
            "description": "Manage note users, roles, and account operations.",
            "url": _admin_target(current_app.config["NOTESTACK_URL"]),
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


def _admin_context(shared_user, is_admin):
    """Shared template context for the platform-admin sub pages."""
    home_path = "/"
    admin_url = _central_admin_url()
    return {
        "shared_user": shared_user,
        "is_admin": is_admin,
        "auth_url": build_auth_handoff_url(
            current_app.config["AUTH_URL"], home_path, current_app.config["AUTH_RETURN_PARAM"]
        ),
        "auth_admin_url": build_auth_handoff_url(
            current_app.config["AUTH_URL"], admin_url, current_app.config["AUTH_RETURN_PARAM"]
        ),
        "logout_url": build_auth_handoff_url(
            current_app.config["LOGOUT_URL"], home_path, current_app.config["AUTH_RETURN_PARAM"]
        ),
        "home_url": home_path,
        "admin_url": admin_url,
    }


@main_bp.get("/users")
def legacy_users_redirect():
    """Redirect legacy bare /users links to the admin hub location."""
    return redirect(_central_admin_url() + "/users", code=301)


@main_bp.get("/logs")
def legacy_logs_redirect():
    """Redirect legacy bare /logs links to the admin hub location."""
    return redirect(_central_admin_url() + "/logs", code=301)


@main_bp.get("/platform-admin/users")
def admin_users():
    shared_user = _fetch_shared_auth_user()
    is_admin = bool(shared_user and shared_user.get("is_admin"))
    query = (request.args.get("q") or "").strip()
    page = request.args.get("page", "1")

    users, total, pages, error = [], 0, 1, None
    if is_admin:
        status, payload = _call_auth_admin("GET", "/admin/users", params={"q": query, "page": page})
        if status == 200 and isinstance(payload, dict):
            users = payload.get("users", [])
            total = payload.get("total", 0)
            pages = payload.get("pages", 1)
        elif status is None:
            error = payload.get("error_description", "Could not reach the auth service")

    ctx = _admin_context(shared_user, is_admin)
    ctx.update(
        users=users,
        query=query,
        total=total,
        pages=pages,
        page=int(page) if str(page).isdigit() else 1,
        error=error,
    )
    return render_template("admin_users.html", **ctx)


@main_bp.get("/platform-admin/users/<int:user_id>")
def admin_user_detail(user_id):
    shared_user = _fetch_shared_auth_user()
    is_admin = bool(shared_user and shared_user.get("is_admin"))

    detail, error = None, None
    if is_admin:
        status, payload = _call_auth_admin("GET", f"/admin/users/{user_id}")
        if status == 200 and isinstance(payload, dict):
            detail = payload
        elif status == 404:
            error = "User not found."
        elif status is None:
            error = payload.get("error_description", "Could not reach the auth service")

    ctx = _admin_context(shared_user, is_admin)
    ctx.update(detail=detail, error=error, user_id=user_id)
    return render_template("admin_user_detail.html", **ctx)


@main_bp.post("/platform-admin/users/<int:user_id>/role")
def admin_user_role_action(user_id):
    shared_user = _fetch_shared_auth_user()
    if not (shared_user and shared_user.get("is_admin")):
        return redirect(url_for("main.admin_users"))

    is_admin_flag = request.form.get("is_admin") in ("1", "true", "on")
    _call_auth_admin("POST", f"/admin/users/{user_id}/role", json_body={"is_admin": is_admin_flag})
    flash("User role updated.", "success")
    return redirect(url_for("main.admin_user_detail", user_id=user_id))


@main_bp.post("/platform-admin/users/<int:user_id>/reset-password")
def admin_user_reset_action(user_id):
    shared_user = _fetch_shared_auth_user()
    if not (shared_user and shared_user.get("is_admin")):
        return redirect(url_for("main.admin_user_detail", user_id=user_id))

    new_password = request.form.get("password", "")
    status, payload = _call_auth_admin(
        "POST", f"/admin/users/{user_id}/reset-password", json_body={"password": new_password}
    )
    if status == 200:
        flash("Password updated.", "success")
    else:
        message = (payload or {}).get("error_description", "Could not reset password.")
        flash(message, "error")
    return redirect(url_for("main.admin_user_detail", user_id=user_id))


@main_bp.post("/platform-admin/users/<int:user_id>/revoke-sessions")
def admin_user_revoke_action(user_id):
    shared_user = _fetch_shared_auth_user()
    if not (shared_user and shared_user.get("is_admin")):
        return redirect(url_for("main.admin_user_detail", user_id=user_id))

    _call_auth_admin("POST", f"/admin/users/{user_id}/revoke-sessions")
    flash("All sessions revoked.", "success")
    return redirect(url_for("main.admin_user_detail", user_id=user_id))


@main_bp.post("/platform-admin/users/<int:user_id>/delete")
def admin_user_delete_action(user_id):
    shared_user = _fetch_shared_auth_user()
    if not (shared_user and shared_user.get("is_admin")):
        return redirect(url_for("main.admin_users"))

    status, payload = _call_auth_admin("DELETE", f"/admin/users/{user_id}")
    if status == 200:
        flash("User deleted.", "success")
    else:
        message = (payload or {}).get("error_description", "Could not delete user.")
        flash(message, "error")
    return redirect(url_for("main.admin_users"))


@main_bp.get("/platform-admin/logs")
def admin_logs():
    shared_user = _fetch_shared_auth_user()
    is_admin = bool(shared_user and shared_user.get("is_admin"))

    activity, clients, stats, error = [], [], {}, None
    if is_admin:
        status, payload = _call_auth_admin("GET", "/admin/logs")
        if status == 200 and isinstance(payload, dict):
            activity = payload.get("activity", [])
            clients = payload.get("clients", [])
            stats = payload.get("stats", {})
        elif status is None:
            error = payload.get("error_description", "Could not reach the auth service")

    ctx = _admin_context(shared_user, is_admin)
    ctx.update(activity=activity, clients=clients, stats=stats, error=error)
    return render_template("admin_logs.html", **ctx)


@main_bp.get("/login")
def login_redirect():
    return redirect(
        build_auth_handoff_url(
            current_app.config["AUTH_URL"],
            "/",
            current_app.config["AUTH_RETURN_PARAM"],
        )
    )


@main_bp.get("/curio")
@main_bp.get("/curio/")
def legacy_curio_redirect():
    """Keep legacy Curio links working after the rename to Neera."""
    return redirect(current_app.config["NEERA_URL"])


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
