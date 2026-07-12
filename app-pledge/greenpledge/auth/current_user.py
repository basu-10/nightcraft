from dataclasses import dataclass

from flask import current_app, session
from flask_login import current_user as flask_login_current_user

from ..models import UserProfile


@dataclass(frozen=True)
class AppUser:
    user_id: str
    username: str
    is_admin: bool
    is_authenticated: bool
    timezone_name: str


def _anonymous_user(default_timezone):
    return AppUser(
        user_id="",
        username="",
        is_admin=False,
        is_authenticated=False,
        timezone_name=default_timezone,
    )


def _from_local(default_timezone):
    user = flask_login_current_user
    if not getattr(user, "is_authenticated", False):
        return _anonymous_user(default_timezone)

    return AppUser(
        user_id=str(user.get_id() or ""),
        username=getattr(user, "username", "") or "",
        is_admin=bool(getattr(user, "is_admin", False)),
        is_authenticated=True,
        timezone_name=getattr(user, "timezone_name", default_timezone) or default_timezone,
    )


def _from_sso(default_timezone):
    user_id = session.get("user_id")
    if not user_id:
        return _anonymous_user(default_timezone)

    profile = UserProfile.query.filter_by(user_id=str(user_id)).first()
    if not profile:
        return _anonymous_user(default_timezone)

    return AppUser(
        user_id=profile.user_id,
        username=profile.username or session.get("username", "") or "",
        is_admin=bool(profile.is_admin),
        is_authenticated=True,
        timezone_name=profile.timezone_name or default_timezone,
    )


def get_current_user():
    default_timezone = current_app.config.get("DEFAULT_TIMEZONE", "Asia/Kolkata")
    auth_mode = current_app.config.get("AUTH_MODE", "local").lower()
    if auth_mode == "sso":
        return _from_sso(default_timezone)
    return _from_local(default_timezone)
