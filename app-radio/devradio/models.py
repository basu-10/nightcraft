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
    role = db.Column(db.String(20), nullable=False, default="listener")

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

    saves = db.relationship("SavedStory", back_populates="user_profile", cascade="all, delete-orphan")


@login_manager.user_loader
def load_user(user_id):
    try:
        local_id = int(user_id)
    except (TypeError, ValueError):
        return None
    return db.session.get(LocalCredential, local_id)


class Channel(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)

    articles = db.relationship("Article", back_populates="channel")
    segments = db.relationship("Segment", back_populates="channel")
    automated_source_allocations = db.relationship(
        "AutomatedSourceAllocation",
        back_populates="channel",
        cascade="all, delete-orphan",
    )


class Article(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channel.id"), nullable=False)
    source_name = db.Column(db.String(120), nullable=False)
    source_url = db.Column(db.String(500), nullable=False, unique=True)
    image_url = db.Column(db.String(1000), nullable=True)
    title = db.Column(db.String(300), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    raw_excerpt = db.Column(db.Text, nullable=True)
    source_full_article = db.Column(db.Text, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="staged")
    short_headline = db.Column(db.String(160), nullable=True)
    bullet_summary = db.Column(db.Text, nullable=True)
    narration_script = db.Column(db.Text, nullable=True)
    tags = db.Column(db.String(250), nullable=True)
    internal_content = db.Column(db.Text, nullable=True)
    no_ai_mode = db.Column(db.Boolean, nullable=False, default=False)

    channel = db.relationship("Channel", back_populates="articles")
    segment = db.relationship("Segment", back_populates="article", uselist=False)
    saves = db.relationship("SavedStory", back_populates="article", cascade="all, delete-orphan")


class Segment(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), unique=True, nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey("channel.id"), nullable=False)
    scheduled_at_utc = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    audio_url = db.Column(db.String(500), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    transcript = db.Column(db.Text, nullable=True)
    tts_model = db.Column(db.String(80), nullable=True)

    article = db.relationship("Article", back_populates="segment")
    channel = db.relationship("Channel", back_populates="segments")


class SourceFeed(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channel.id"), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    feed_url = db.Column(db.String(500), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="rss")
    active = db.Column(db.Boolean, default=True, nullable=False)
    automated_last_published_at = db.Column(db.DateTime, nullable=True)
    automated_allocation = db.relationship(
        "AutomatedSourceAllocation",
        back_populates="source_feed",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AutomatedSourceAllocation(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey("channel.id"), nullable=False)
    source_feed_id = db.Column(db.Integer, db.ForeignKey("source_feed.id"), nullable=False, unique=True)

    channel = db.relationship("Channel", back_populates="automated_source_allocations")
    source_feed = db.relationship("SourceFeed", back_populates="automated_allocation")


class AppSetting(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    encrypted = db.Column(db.Boolean, nullable=False, default=False)


class SavedStory(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_profile.id"), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id"), nullable=False)

    user_profile = db.relationship("UserProfile", back_populates="saves")
    article = db.relationship("Article", back_populates="saves")

    __table_args__ = (db.UniqueConstraint("user_id", "article_id", name="uq_user_article_save"),)
