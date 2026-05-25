"""
Configuration classes for NoteStack Web.
Select via FLASK_ENV environment variable (development / production).
"""
import os
import secrets

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_or_create_dev_key() -> str:
    """Return a stable dev secret key, persisted in .dev_secret_key (gitignored)."""
    key_file = os.path.join(_BASE_DIR, ".dev_secret_key")
    if os.path.isfile(key_file):
        try:
            key = open(key_file).read().strip()
            if key:
                return key
        except OSError:
            pass
    key = secrets.token_hex(32)
    try:
        with open(key_file, "w") as f:
            f.write(key)
    except OSError:
        pass
    return key


class Config:
    # Override with a stable secret in production via FLASK_SECRET_KEY env var
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY") or _load_or_create_dev_key()
    DB_PATH: str = os.environ.get("NOTESTACK_DB") or os.path.join(_BASE_DIR, "notestack.db")
    AUTH_MODE: str = os.environ.get("AUTH_MODE", "local").strip().lower() or "local"
    AUTH_SERVICE_URL: str = os.environ.get("AUTH_SERVICE_URL", "http://127.0.0.1:5100")
    AUTH_SESSION_ME_URL: str = os.environ.get("AUTH_SESSION_ME_URL", "")
    SESSION_COOKIE_NAME: str = os.environ.get("SESSION_COOKIE_NAME", "nightcraft_notestack_session")
    SESSION_COOKIE_PATH: str = os.environ.get("SESSION_COOKIE_PATH", "/")
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    # In production (HTTPS) set this to True via env or subclass
    SESSION_COOKIE_SECURE: bool = os.environ.get("FLASK_SESSION_SECURE", "0") == "1"
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB max upload


class DevelopmentConfig(Config):
    DEBUG: bool = True


class ProductionConfig(Config):
    DEBUG: bool = False
    SESSION_COOKIE_SECURE: bool = True


_ENV_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config() -> Config:
    env = os.environ.get("FLASK_ENV", "development").lower()
    return _ENV_MAP.get(env, DevelopmentConfig)()
