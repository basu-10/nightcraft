import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, redirect, send_from_directory, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from .api import api_bp
from .admin import admin_bp
from .auth import auth_bp
from .auth.routes import bridge_shared_auth_session, init_sso
from .config import Config
from .core.activity_log import init_logger
from .extensions import cors, db, login_manager, migrate
from .main import main_bp
from .models import User


load_dotenv()


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(user_id)


def _enforce_postgres_database_uri(app: Flask) -> None:
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


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    _enforce_postgres_database_uri(app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    frontend_dist = os.getenv("SEEKSAGE_FRONTEND_DIST", "").strip()
    if frontend_dist:
        frontend_dist_dir = Path(frontend_dist)
    else:
        frontend_dist_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    app.config["FRONTEND_DIST_DIR"] = str(frontend_dist_dir)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    init_sso(app)
    cors.init_app(
        app,
        supports_credentials=True,
        origins=app.config["CORS_ORIGINS"],
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)

    if app.config.get("AUTH_MODE", "local") == "sso":
        @app.before_request
        def bridge_sso_session():
            bridge_shared_auth_session()

    @app.get("/")
    def root():
        if app.config.get("SEEKSAGE_UI_AT_ROOT", False):
            return redirect(url_for("main.ui_root"))

        if frontend_dist_dir.is_dir() and (frontend_dist_dir / "index.html").is_file():
            return send_from_directory(frontend_dist_dir, "index.html")
        return {
            "name": "SeekSage Web API",
            "authenticated": current_user.is_authenticated,
        }

    @app.get("/<path:path>")
    def frontend(path: str):
        if path.startswith(("api/", "auth/", "admin/")):
            abort(404)

        if frontend_dist_dir.is_dir() and (frontend_dist_dir / path).is_file():
            return send_from_directory(frontend_dist_dir, path)

        if frontend_dist_dir.is_dir() and (frontend_dist_dir / "index.html").is_file():
            return send_from_directory(frontend_dist_dir, "index.html")

        abort(404)

    with app.app_context():
        db.create_all()

    # Initialise activity logger on the same PostgreSQL database.
    init_logger(app.config["SQLALCHEMY_DATABASE_URI"])

    return app
