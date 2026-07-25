"""Flask app factory for the admin handoff app."""
from flask import Flask, g, redirect, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from .auth_utils import fetch_shared_auth_user
from .routes import main_bp
from .telemetry import telemetry_bp


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config.from_object(get_config())

    @app.before_request
    def _load_user():
        shared_user = fetch_shared_auth_user()
        g.shared_user = shared_user
        g.is_admin = bool(shared_user and shared_user.get("is_admin"))

    @app.before_request
    def _enforce_admin():
        if request.path.startswith("/admin/telemetry"):
            if not g.get("is_admin"):
                return redirect(url_for("main.admin_handoff"))

    app.register_blueprint(main_bp)
    app.register_blueprint(telemetry_bp)
    return app
