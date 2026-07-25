"""Configuration for the admin handoff app."""
import os
import secrets

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_or_create_dev_key() -> str:
    """Return a stable dev secret key persisted in .dev_secret_key."""
    key_file = os.path.join(_BASE_DIR, ".dev_secret_key")
    if os.path.isfile(key_file):
        try:
            key = open(key_file, encoding="utf-8").read().strip()
            if key:
                return key
        except OSError:
            pass

    key = secrets.token_hex(32)
    try:
        with open(key_file, "w", encoding="utf-8") as handle:
            handle.write(key)
    except OSError:
        pass
    return key


class Config:
    SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY") or _load_or_create_dev_key()
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = os.environ.get("FLASK_SESSION_SECURE", "0") == "1"

    AUTH_URL: str = os.environ.get("ADMIN_AUTH_URL", "/auth/login")
    AUTH_RETURN_PARAM: str = os.environ.get("ADMIN_AUTH_RETURN_PARAM", "next")
    ADMIN_RETURN_PATH: str = os.environ.get("ADMIN_RETURN_PATH", "/admin")
    TELEMETRY_DATABASE_URL: str = os.environ.get("TELEMETRY_DATABASE_URL", "")


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
