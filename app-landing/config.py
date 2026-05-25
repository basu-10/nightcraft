"""Configuration for the landing app."""
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

    # Path-based defaults expected behind nginx on the same host.
    AUTH_URL: str = os.environ.get("LANDING_AUTH_URL", "/auth/login")
    LOGOUT_URL: str = os.environ.get("LANDING_LOGOUT_URL", "/auth/logout")
    AUTH_SESSION_ME_URL: str = os.environ.get("LANDING_AUTH_SESSION_ME_URL", "/auth/session/me")
    AUTH_RETURN_PARAM: str = os.environ.get("LANDING_AUTH_RETURN_PARAM", "next")
    ADMIN_URL: str = os.environ.get("LANDING_ADMIN_URL", "/admin")
    DEVRADIO_URL: str = os.environ.get("LANDING_DEVRADIO_URL", "/devradio")
    CURIO_URL: str = os.environ.get("LANDING_CURIO_URL", "/curio")
    SEEKSAGE_URL: str = os.environ.get("LANDING_SEEKSAGE_URL", "/seeksage")
    GAME_URL: str = os.environ.get("LANDING_GAME_URL", "/game")
    NOTESTACK_URL: str = os.environ.get("LANDING_NOTESTACK_URL", "/notestack")


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
