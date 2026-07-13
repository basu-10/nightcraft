import os
import secrets

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_or_create_dev_key() -> str:
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
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or _load_or_create_dev_key()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_SESSION_SECURE", "0") == "1"

    REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    ROOM_EXPIRY = int(os.environ.get("GAME_ROOM_EXPIRY", "3600"))
    QUEUE_TIMEOUT = int(os.environ.get("GAME_QUEUE_TIMEOUT", "120"))
    QUEUE_TTL = int(os.environ.get("GAME_QUEUE_TTL", "60"))
    DISCONNECT_TIMEOUT = int(os.environ.get("GAME_DISCONNECT_TIMEOUT", "30"))
    ROUNDS_PER_MATCH = int(os.environ.get("GAME_ROUNDS_PER_MATCH", "5"))
    WINS_REQUIRED = int(os.environ.get("GAME_WINS_REQUIRED", "3"))

    AUTH_MODE = os.environ.get("AUTH_MODE", "local")
    AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://127.0.0.1/auth")
    OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "game-app")
    OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
    OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "/game/auth/callback")

    # Persistent shared volume (kept outside the gitignored source checkout).
    GAME_SHARED_DIR = os.environ.get("GAME_SHARED_DIR", "/runtime/shared/app-game")
    EMULATOR_UPLOAD_DIR = os.path.join(GAME_SHARED_DIR, "uploads")
    EMULATOR_DB_PATH = os.path.join(GAME_SHARED_DIR, "emulator.db")

    # ROM upload limits.
    MAX_CONTENT_LENGTH = int(os.environ.get("GAME_MAX_UPLOAD_MB", "64")) * 1024 * 1024
    EMULATOR_MAX_ROMS = int(os.environ.get("GAME_EMULATOR_MAX_ROMS", "20"))
    EMULATOR_MAX_STORAGE_BYTES = int(os.environ.get("GAME_EMULATOR_MAX_STORAGE_MB", "512")) * 1024 * 1024

    # User IDs (comma-separated) allowed to remove any ROM for DMCA takedowns.
    GAME_ADMIN_USER_IDS = [
        u.strip() for u in os.environ.get("GAME_ADMIN_USER_IDS", "").split(",") if u.strip()
    ]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


_ENV_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    return _ENV_MAP.get(env, DevelopmentConfig)()
