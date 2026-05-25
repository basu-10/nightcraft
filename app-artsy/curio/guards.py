from functools import wraps
from urllib.parse import urlsplit

from flask import redirect, request, url_for

from .auth.current_user import get_current_user


def _forwarded_prefix() -> str:
    raw_prefix = (request.headers.get("X-Forwarded-Prefix") or "").strip()
    if not raw_prefix:
        return ""
    normalized = f"/{raw_prefix.strip('/')}"
    return "" if normalized == "/" else normalized


def _normalize_next_target(raw_target: str | None, fallback: str) -> str:
    candidate = (raw_target or fallback or "/").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        candidate = fallback
        parsed = urlsplit(candidate)

    path = parsed.path or "/"
    prefix = _forwarded_prefix()
    if prefix and path != prefix and not path.startswith(f"{prefix}/"):
        path = f"{prefix}{path}" if path.startswith("/") else f"{prefix}/{path}"

    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user.is_authenticated:
            return view(*args, **kwargs)

        login_url = url_for("auth.login")
        if request.method == "GET":
            next_target = request.full_path if request.query_string else request.path
            next_target = _normalize_next_target(next_target, request.path)
            return redirect(url_for("auth.login", next=next_target))
        return redirect(login_url)

    return wrapped
