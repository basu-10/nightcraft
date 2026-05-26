import os
import threading
import time

from flask import Flask
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import db, login_manager
from .models import Channel
from .services.crypto import EncryptionService
from .utils import format_in_app_timezone


def _acquire_process_lock(lock_path: str):
    """Acquire a non-blocking process lock; returns a file handle when acquired."""
    try:
        import fcntl  # Linux production path
    except ImportError:
        return None

    lock_file = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except OSError:
        lock_file.close()
        return None


def _release_process_lock(lock_file) -> None:
    if lock_file is None:
        return

    try:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    finally:
        try:
            lock_file.close()
        except Exception:
            pass


def _start_automated_worker(app):
    if app.config.get("TESTING"):
        return

    if not app.config.get("AUTOMATED_BACKGROUND_ENABLED", True):
        return

    # With Flask debug reloader, only start worker in the active child process.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    if app.extensions.get("automated_worker_started"):
        return

    interval_seconds = int(app.config.get("AUTOMATED_INGEST_INTERVAL_SECONDS", 3600))
    lock_path = app.config.get("AUTOMATED_WORKER_LOCK_FILE") or os.path.join(
        app.instance_path,
        "automated_ingestion.lock",
    )
    os.makedirs(app.instance_path, exist_ok=True)

    def _worker_loop():
        while True:
            lock_file = None
            try:
                with app.app_context():
                    lock_file = _acquire_process_lock(lock_path)
                    if lock_file is None:
                        app.logger.debug("Automated ingestion skipped in this worker because lock is held")
                        time.sleep(max(60, interval_seconds))
                        continue

                    from .services.automation import run_automated_ingestion

                    run_automated_ingestion()
            except Exception:
                app.logger.exception("Automated ingestion worker iteration failed")
            finally:
                _release_process_lock(lock_file)
                try:
                    db.session.remove()
                except Exception:
                    pass
            time.sleep(max(60, interval_seconds))

    worker = threading.Thread(target=_worker_loop, name="devradio-automated-worker", daemon=True)
    worker.start()
    app.extensions["automated_worker_started"] = True


def _enforce_postgres_database_uri(app):
    database_uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not database_uri:
        raise RuntimeError("FLASK_SQLALCHEMY_DATABASE_URI must be set to a PostgreSQL DSN.")

    if not database_uri.startswith(
        ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://", "postgres://")
    ):
        raise RuntimeError("DevRadio supports PostgreSQL only. Set FLASK_SQLALCHEMY_DATABASE_URI to a PostgreSQL DSN.")

    # Prefer psycopg v3 driver URLs so SQLAlchemy does not attempt psycopg2 imports.
    if database_uri.startswith("postgres://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgres://") :]
    elif database_uri.startswith("postgresql://"):
        database_uri = "postgresql+psycopg://" + database_uri[len("postgresql://") :]

    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri


def _ensure_schema_compatibility(app):
    try:
        inspector = inspect(db.engine)
        if "article" in inspector.get_table_names():
            article_columns = {col["name"] for col in inspector.get_columns("article")}
            if "source_full_article" not in article_columns:
                db.session.execute(text("ALTER TABLE article ADD COLUMN source_full_article TEXT"))
                db.session.commit()

            db.session.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_article_source_url_unique ON article(source_url)")
            )
            db.session.commit()

        if "source_feed" in inspector.get_table_names():
            source_feed_columns = {col["name"] for col in inspector.get_columns("source_feed")}
            if "automated_last_published_at" not in source_feed_columns:
                db.session.execute(text("ALTER TABLE source_feed ADD COLUMN automated_last_published_at TIMESTAMP"))
                db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not apply schema compatibility adjustments")


def create_app(test_config=None, instance_path=None):
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config.from_mapping(
        SECRET_KEY="dev-secret",
        AUTH_MODE="local",
        SESSION_COOKIE_NAME="nightcraft_devradio_session",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", ""),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        DEFAULT_TIMEZONE="Asia/Kolkata",
        SOURCE_FETCH_ENABLED=True,
        SOURCE_FETCH_USER_AGENT="DevRadioBot/1.0 (+https://devradio.local)",
        SOURCE_FETCH_TIMEOUT_SECONDS=12.0,
        SOURCE_FETCH_MIN_CHARS=800,
        SOURCE_FETCH_MAX_CHARS=30000,
        SOURCE_FETCH_MIN_DELAY_SECONDS=2.0,
        SOURCE_FETCH_JITTER_SECONDS=1.0,
        SOURCE_FETCH_MAX_RETRIES=2,
        SOURCE_FETCH_RETRY_BACKOFF_SECONDS=2.0,
        SOURCE_FETCH_RESPECT_ROBOTS=True,
        AUTOMATED_BACKGROUND_ENABLED=True,
        AUTOMATED_INGEST_INTERVAL_SECONDS=3600,
        AUTOMATED_SEGMENT_SPACING_MINUTES=8,
        AUTOMATED_LOG_MAX_RUN_FILES=500,
        AUTOMATED_LOG_MAX_JSONL_LINES=5000,
        BREAKING_LOG_MAX_JSONL_LINES=5000,
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
    from .admin import bp as admin_bp
    from .listener import bp as listener_bp
    from .cli import register_cli, _seed_channels_and_feeds

    auth_bp = get_auth_blueprint(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(listener_bp)

    register_cli(app)

    @app.template_filter("app_tz")
    def app_timezone_filter(value, fmt="%Y-%m-%d %H:%M:%S %Z"):
        return format_in_app_timezone(value, fmt)

    @app.context_processor
    def inject_globals():
        from .auth.current_user import get_current_user

        channels = Channel.query.order_by(Channel.name.asc()).all()
        return {
            "channels": channels,
            "default_timezone": app.config.get("DEFAULT_TIMEZONE", "Asia/Kolkata"),
            "app_user": get_current_user(),
            "has_admin_login": "auth.admin_login" in app.view_functions,
        }

    with app.app_context():
        db.create_all()
        _ensure_schema_compatibility(app)
        _seed_channels_and_feeds()

    EncryptionService.configure(app)
    _start_automated_worker(app)

    return app
