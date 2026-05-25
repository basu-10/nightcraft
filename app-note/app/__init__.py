"""Flask application factory."""
from flask import Flask, g, session
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from .database import initialize_db
from .sync_logging import get_sync_logger
from .auth import get_auth_blueprint


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    cfg = get_config()
    app.config.from_object(cfg)
    get_sync_logger()

    # Expose DB configuration to database helpers
    from . import database as _db_mod
    _db_mod.configure_database(cfg)

    with app.app_context():
        initialize_db()

    # ── Blueprints ──────────────────────────────────────────────────────────
    from .api.routes import api_bp
    from .main.routes import main_bp

    auth_bp = get_auth_blueprint(app)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(main_bp)

    @app.before_request
    def _load_user():
        g.user_id = session.get("user_id")

    if app.config.get("AUTH_MODE", "local") == "sso":
        from .auth.sso_auth import ensure_session_from_shared_auth

        @app.before_request
        def _bridge_shared_session():
            ensure_session_from_shared_auth()

    return app
