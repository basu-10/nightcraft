from pathlib import Path
import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import get_auth_blueprint
from .cli import register_cli
from .extensions import db, login_manager
from .models import LocalCredential
from .routes import bp as main_bp


def create_app(test_config=None, instance_path=None):
    app_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        instance_path=instance_path,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config.from_mapping(
        SECRET_KEY="dev-secret",
        AUTH_MODE="local",
        SESSION_COOKIE_NAME="nightcraft_curio_session",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", ""),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTH_SERVICE_URL="http://127.0.0.1:5100",
        AUTHLIB_CLIENT_ID="curio-app",
        AUTHLIB_CLIENT_SECRET="dev-secret",
        AUTH_LOGIN_PATH="/auth/login",
        ADMIN_APP_PATH="/admin",
        LANDING_ADMIN_URL="/platform-admin",
        AUTH_RETURN_PARAM="next",
        UPLOADS_DIR="uploads",
    )

    if test_config:
        app.config.update(test_config)
    else:
        app.config.from_prefixed_env()

    _enforce_postgres_database_uri(app)

    db.init_app(app)

    if app.config.get("AUTH_MODE", "local").lower() == "local":
        login_manager.init_app(app)

        @login_manager.user_loader
        def load_user(user_id):
            return LocalCredential.query.get(int(user_id))

    auth_bp = get_auth_blueprint(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    register_cli(app)

    if app.config.get("AUTH_MODE", "local").lower() == "sso":
        from .auth.sso_auth import ensure_session_from_shared_auth

        @app.before_request
        def bridge_shared_sso_session():
            ensure_session_from_shared_auth()

    @app.context_processor
    def inject_app_user():
        from .auth.current_user import get_current_user

        return {"app_user": get_current_user()}

    with app.app_context():
        db.create_all()

    return app


def _enforce_postgres_database_uri(app):
    database_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri:
        raise RuntimeError("DATABASE_URL must be set to a PostgreSQL DSN.")

    if not database_uri.startswith(
        ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://", "postgres://")
    ):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL DSN (postgresql://...).")

    # Prefer psycopg v3 driver URLs so SQLAlchemy does not attempt psycopg2 imports.
    if database_uri.startswith("postgres://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgres://") :]
    elif database_uri.startswith("postgresql://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgresql://") :]

    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
