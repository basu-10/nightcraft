import os

from flask import Flask
from sqlalchemy import inspect
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import db, login_manager
from .models import LocalCredential, UserProfile


def _enforce_postgres_database_uri(app):
    database_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri:
        raise RuntimeError("FLASK_SQLALCHEMY_DATABASE_URI must be set to a PostgreSQL DSN.")

    if not database_uri.startswith(
        ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://", "postgres://")
    ):
        raise RuntimeError(
            "The Green Pledge supports PostgreSQL only. "
            "Set FLASK_SQLALCHEMY_DATABASE_URI to a PostgreSQL DSN."
        )

    # Prefer psycopg v3 driver URLs so SQLAlchemy does not attempt psycopg2 imports.
    if database_uri.startswith("postgres://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgres://") :]
    elif database_uri.startswith("postgresql://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgresql://") :]

    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri


def create_app(test_config=None, instance_path=None):
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config.from_mapping(
        SECRET_KEY="dev-secret",
        AUTH_MODE="local",
        SESSION_COOKIE_NAME="nightcraft_pledge_session",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", ""),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        DEFAULT_TIMEZONE="Asia/Kolkata",
    )

    if test_config:
        app.config.update(test_config)
    else:
        app.config.from_prefixed_env()

    _enforce_postgres_database_uri(app)

    db.init_app(app)
    if app.config.get("AUTH_MODE", "local").lower() == "local":
        login_manager.init_app(app)

    from .auth import get_auth_blueprint
    from .landing import bp as landing_bp
    from .cli import register_cli

    auth_bp = get_auth_blueprint(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(landing_bp)

    register_cli(app)

    @app.template_filter("app_tz")
    def app_timezone_filter(value, fmt="%Y-%m-%d %H:%M:%S %Z"):
        from .utils import format_in_app_timezone

        return format_in_app_timezone(value, fmt)

    @app.context_processor
    def inject_globals():
        from .auth.current_user import get_current_user

        return {
            "app_name": "The Green Pledge",
            "default_timezone": app.config.get("DEFAULT_TIMEZONE", "Asia/Kolkata"),
            "app_user": get_current_user(),
            "has_admin_login": "auth.admin_login" in app.view_functions,
        }

    with app.app_context():
        db.create_all()

    return app
