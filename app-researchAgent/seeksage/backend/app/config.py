import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {}

    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    CORS_ORIGINS = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "nightcraft_seeksage_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    # Auth mode can be local (default) or sso.
    AUTH_MODE = os.getenv("AUTH_MODE", "local").strip().lower()
    AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:5100")
    AUTH_SESSION_ME_URL = os.getenv("AUTH_SESSION_ME_URL", "")
    AUTHLIB_CLIENT_ID = os.getenv("AUTHLIB_CLIENT_ID", "seeksage-app")
    AUTHLIB_CLIENT_SECRET = os.getenv("AUTHLIB_CLIENT_SECRET", "dev-secret")
    SSO_DEFAULT_NEXT = os.getenv("SSO_DEFAULT_NEXT", "/")
