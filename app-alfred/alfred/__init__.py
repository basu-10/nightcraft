from pathlib import Path
import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import get_auth_blueprint
from .extensions import db, login_manager
from .services.crypto import EncryptionService
from .services.settings import get_setting


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
        SESSION_COOKIE_NAME="nightcraft_alfred_session",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", ""),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTH_SERVICE_URL="http://127.0.0.1:5100",
        AUTHLIB_CLIENT_ID="alfred-app",
        AUTHLIB_CLIENT_SECRET="dev-secret",
        AUTH_LOGIN_PATH="/auth/login",
        ADMIN_APP_PATH="/admin",
        AUTH_RETURN_PARAM="next",
        UPLOADS_DIR="uploads",
        OPENROUTER_API_BASE="https://openrouter.ai/api/v1",
        RUNTIME_MANAGER_URL="http://127.0.0.1:5700",
        APP_SLUG="alfred",
    )

    if test_config:
        app.config.update(test_config)
    else:
        app.config.from_prefixed_env()

    _enforce_postgres_database_uri(app)

    db.init_app(app)

    EncryptionService.configure(app)

    if app.config.get("AUTH_MODE", "local").lower() == "local":
        login_manager.init_app(app)

        @login_manager.user_loader
        def load_user(user_id):
            return LocalCredential_local_query(user_id)

    auth_bp = get_auth_blueprint(app)
    app.register_blueprint(auth_bp)

    from . import routes as routes_module

    app.register_blueprint(routes_module.bp)
    app.register_blueprint(routes_module._root_bp)

    from . import admin as admin_module

    app.register_blueprint(admin_module.bp)

    from . import api as api_module

    app.register_blueprint(api_module.bp)

    from . import library as library_module

    app.register_blueprint(library_module.bp)

    from .keepalive import configure as configure_keepalive

    configure_keepalive(app)

    from .cli import register_cli

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
        _ensure_pgvector(app)
        db.create_all()
        _mark_interrupted_runs()

    return app


def LocalCredential_local_query(user_id):
    from .models import LocalCredential

    return LocalCredential.query.get(int(user_id))


def _enforce_postgres_database_uri(app):
    database_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri:
        raise RuntimeError("DATABASE_URL must be set to a PostgreSQL DSN.")

    if not database_uri.startswith(
        ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://", "postgres://")
    ):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL DSN (postgresql://...).")

    if database_uri.startswith("postgres://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgres://") :]
    elif database_uri.startswith("postgresql://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgresql://") :]

    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri


def _ensure_pgvector(app):
    try:
        with db.engine.begin() as conn:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception as exc:  # pragma: no cover - environment dependent
        app.logger.warning(f"pgvector extension could not be enabled: {exc}")


def _mark_interrupted_runs():
    """Startup sweep: runs left running by a dead process are interrupted."""
    from .models import AgentRun

    try:
        interrupted = (
            AgentRun.query.filter(AgentRun.status.in_(["queued", "running"]))
            .update({AgentRun.status: "error", AgentRun.error: "Run interrupted by service restart."}, synchronize_session=False)
        )
        if interrupted:
            db.session.commit()
    except Exception:
        db.session.rollback()
