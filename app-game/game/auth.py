from functools import wraps
from urllib.parse import urlencode

from flask import (
    Blueprint,
    current_app,
    jsonify,
    make_response,
    redirect,
    request,
    session,
    url_for,
)

auth_bp = Blueprint("game_auth", __name__, url_prefix="/game/auth")


def _get_user_id():
    return session.get("user_id")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_app.config.get("AUTH_MODE") == "sso":
            if not _get_user_id():
                session["next_url"] = request.url
                return redirect(url_for("game_auth.login"))
        else:
            if not _get_user_id():
                session["user_id"] = f"local_{request.remote_addr}"
                session["user_name"] = "Guest"
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login")
def login():
    if current_app.config.get("AUTH_MODE") == "sso":
        auth_url = current_app.config["AUTH_SERVICE_URL"].rstrip("/")
        client_id = current_app.config["OIDC_CLIENT_ID"]
        redirect_uri = current_app.config["OIDC_REDIRECT_URI"]
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid profile email",
            }
        )
        authorize_url = f"{auth_url}/oauth/authorize?{query}"
        return redirect(authorize_url)

    session["user_id"] = f"local_{request.remote_addr}"
    session["user_name"] = "Guest"
    next_url = session.pop("next_url", None) or url_for("game.landing")
    return redirect(next_url)


@auth_bp.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing authorization code"}), 400

    auth_url = current_app.config["AUTH_SERVICE_URL"].rstrip("/")
    client_id = current_app.config["OIDC_CLIENT_ID"]
    client_secret = current_app.config["OIDC_CLIENT_SECRET"]
    redirect_uri = current_app.config["OIDC_REDIRECT_URI"]

    try:
        import requests

        resp = requests.post(
            f"{auth_url}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception:
        return jsonify({"error": "Failed to exchange token"}), 502

    access_token = token_data.get("access_token")
    if not access_token:
        return jsonify({"error": "No access token returned"}), 502

    try:
        import requests

        userinfo_resp = requests.get(
            f"{auth_url}/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    except Exception:
        return jsonify({"error": "Failed to fetch user info"}), 502

    session["user_id"] = userinfo.get("sub") or userinfo.get("user_id")
    session["user_name"] = userinfo.get("name", "Player")

    next_url = session.pop("next_url", None) or url_for("game.landing")
    return redirect(next_url)


@auth_bp.route("/logout")
def logout():
    session.clear()
    if current_app.config.get("AUTH_MODE") == "sso":
        auth_url = current_app.config["AUTH_SERVICE_URL"].rstrip("/")
        return redirect(f"{auth_url}/logout")
    return redirect(url_for("game.landing"))
