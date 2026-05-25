import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import CONFIG_BY_NAME
from .extensions import db, migrate
from .keys import load_or_create_signing_keypair
from .auth_routes import bp as core_bp, init_google_oauth


def _enforce_postgres_database_uri(app):
    database_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri:
        raise RuntimeError("DATABASE_URL must be set to a PostgreSQL DSN.")

    if not database_uri.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL DSN (postgresql://...).")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    env_name = os.getenv("FLASK_ENV", "development").lower()
    config_class = CONFIG_BY_NAME.get(env_name, CONFIG_BY_NAME["development"])
    app.config.from_object(config_class)

    if test_config:
        app.config.update(test_config)

    _enforce_postgres_database_uri(app)

    db.init_app(app)
    migrate.init_app(app, db)
    init_google_oauth(app)

    instance_keys_dir = app.config.get("OIDC_KEYS_DIR", "").strip() or os.path.join(app.instance_path, "keys")
    app.extensions["signing_keys"] = load_or_create_signing_keypair(instance_keys_dir)

    from . import models  # noqa: F401

    app.register_blueprint(core_bp)
    from .cli import register_cli

    register_cli(app)

    @app.get("/")
    def index():
        return {
            "service": "service-auth",
            "message": "Use /.well-known/openid-configuration for OIDC discovery.",
        }

    with app.app_context():
        db.create_all()

    return app
