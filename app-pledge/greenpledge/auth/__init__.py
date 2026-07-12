from .local_auth import bp as local_auth_bp
from .sso_auth import bp as sso_auth_bp, init_sso


def get_auth_blueprint(app):
    auth_mode = app.config.get("AUTH_MODE", "local").lower()
    if auth_mode == "sso":
        init_sso(app)
        return sso_auth_bp
    return local_auth_bp
