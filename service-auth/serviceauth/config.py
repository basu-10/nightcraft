import os


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-to-a-long-random-value-for-local-usage-only-2026")
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "nightcraft_auth_session")
    SESSION_COOKIE_PATH = os.getenv("SESSION_COOKIE_PATH", "/")
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
    OIDC_ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:5100")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")
    OIDC_SIGNING_ALG = os.getenv("OIDC_SIGNING_ALG", "RS256")
    OIDC_KEYS_DIR = os.getenv("OIDC_KEYS_DIR", "")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_DISCOVERY_URL = os.getenv(
        "GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT", "/api/telemetry/v1/events")
    TELEMETRY_DATABASE_URL = os.getenv("TELEMETRY_DATABASE_URL", "")
    TELEMETRY_DISABLED = os.getenv("TELEMETRY_DISABLED", "0") == "1"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "")


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
