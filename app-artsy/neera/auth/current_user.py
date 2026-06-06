from dataclasses import dataclass

from flask import current_app, session
from flask_login import current_user as flask_login_current_user

from ..models import UserProfile


@dataclass(frozen=True)
class AppUser:
    user_id: str
    username: str
    display_name: str
    is_admin: bool
    is_authenticated: bool


def _anonymous_user():
    return AppUser(
        user_id="",
        username="",
        display_name="",
        is_admin=False,
        is_authenticated=False,
    )


def _from_local():
    user = flask_login_current_user
    if not getattr(user, "is_authenticated", False):
        return _anonymous_user()

    profile = UserProfile.query.filter_by(user_id=f"local:{user.get_id()}").first()
    if profile is None:
        profile = user.ensure_profile()

    return AppUser(
        user_id=profile.user_id,
        username=profile.username,
        display_name=profile.display_name,
        is_admin=bool(profile.is_admin),
        is_authenticated=True,
    )


def _from_sso():
    user_id = session.get("user_id")
    if not user_id:
        return _anonymous_user()

    profile = UserProfile.query.filter_by(user_id=str(user_id)).first()
    if profile is None:
        return _anonymous_user()

    return AppUser(
        user_id=profile.user_id,
        username=profile.username,
        display_name=profile.display_name,
        is_admin=bool(profile.is_admin),
        is_authenticated=True,
    )


def get_current_user():
    auth_mode = current_app.config.get("AUTH_MODE", "local").lower()
    if auth_mode == "sso":
        return _from_sso()
    return _from_local()
