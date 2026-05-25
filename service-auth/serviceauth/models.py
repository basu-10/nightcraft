from datetime import datetime, timezone

from .extensions import db
from werkzeug.security import check_password_hash, generate_password_hash


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    timezone_name = db.Column(db.String(64), nullable=False, default="Asia/Kolkata")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Session(TimestampMixin, db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    session_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)


class OauthClient(TimestampMixin, db.Model):
    __tablename__ = "oauth_clients"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    client_secret = db.Column(db.String(255), nullable=False)
    redirect_uris = db.Column(db.Text, nullable=False)
    scope = db.Column(db.String(255), nullable=False, default="openid profile email")
    is_confidential = db.Column(db.Boolean, nullable=False, default=True)


class AuthorizationCode(TimestampMixin, db.Model):
    __tablename__ = "authorization_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    client_id = db.Column(db.String(120), nullable=False, index=True)
    redirect_uri = db.Column(db.String(500), nullable=False)
    scope = db.Column(db.String(255), nullable=False)
    nonce = db.Column(db.String(255), nullable=True)
    code_challenge = db.Column(db.String(255), nullable=True)
    code_challenge_method = db.Column(db.String(20), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)


class RefreshToken(TimestampMixin, db.Model):
    __tablename__ = "refresh_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    client_id = db.Column(db.String(120), nullable=False, index=True)
    scope = db.Column(db.String(255), nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
