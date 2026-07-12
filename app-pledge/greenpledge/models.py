from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LocalCredential(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "local_credential"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")

    def get_user_profile(self):
        return UserProfile.query.filter_by(user_id=str(self.id)).first()

    def ensure_user_profile(self, timezone_name="Asia/Kolkata"):
        profile = self.get_user_profile()
        if not profile:
            profile = UserProfile(
                user_id=str(self.id),
                username=self.username,
                is_admin=self.is_admin,
                timezone_name=timezone_name or "Asia/Kolkata",
            )
            db.session.add(profile)
            return profile

        profile.username = self.username
        profile.is_admin = self.is_admin
        if not profile.timezone_name:
            profile.timezone_name = timezone_name or "Asia/Kolkata"
        return profile

    @property
    def user_profile(self):
        return self.get_user_profile()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def timezone_name(self):
        profile = self.ensure_user_profile()
        if profile and profile.timezone_name:
            return profile.timezone_name
        return "Asia/Kolkata"

    @timezone_name.setter
    def timezone_name(self, value):
        profile = self.ensure_user_profile(timezone_name=value or "Asia/Kolkata")
        timezone_name = value or "Asia/Kolkata"
        profile.timezone_name = timezone_name


class UserProfile(TimestampMixin, db.Model):
    __tablename__ = "user_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(80), nullable=False, default="")
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    timezone_name = db.Column(db.String(64), nullable=False, default="Asia/Kolkata")


@login_manager.user_loader
def load_user(user_id):
    try:
        local_id = int(user_id)
    except (TypeError, ValueError):
        return None
    return db.session.get(LocalCredential, local_id)


class Pledge(TimestampMixin, db.Model):
    """Core product entity for The Green Pledge.

    A pledge represents a commitment a member makes toward a greener lifestyle
    or cause. This is the initial schema the product will be built on top of.
    """

    __tablename__ = "pledge"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    category = db.Column(db.String(80), nullable=False, default="general")
    active = db.Column(db.Boolean, nullable=False, default=True)
