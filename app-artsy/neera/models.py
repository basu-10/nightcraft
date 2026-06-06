from datetime import datetime, UTC

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class LocalCredential(UserMixin, db.Model):
    __tablename__ = "local_credential"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    def ensure_profile(self):
        profile = UserProfile.query.filter_by(user_id=f"local:{self.id}").first()
        if profile:
            return profile

        profile = UserProfile(
            user_id=f"local:{self.id}",
            username=self.username,
            display_name=self.username,
            bio="Curating books, songs, films, and everything in between.",
            is_public=True,
        )
        db.session.add(profile)
        return profile


class UserProfile(db.Model):
    __tablename__ = "user_profile"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    bio = db.Column(db.Text, nullable=False, default="")
    location = db.Column(db.String(140), nullable=False, default="")
    profile_link = db.Column(db.String(500), nullable=False, default="")
    avatar_url = db.Column(db.String(500), nullable=False, default="")
    background_url = db.Column(db.String(500), nullable=False, default="")
    accent_color = db.Column(db.String(20), nullable=False, default="#151515")
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    timezone_name = db.Column(db.String(60), nullable=False, default="Asia/Kolkata")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    lists = db.relationship("NeeraList", back_populates="profile", cascade="all, delete-orphan")
    reviews = db.relationship("Review", back_populates="profile", cascade="all, delete-orphan")
    notes = db.relationship("NeeraNote", back_populates="profile", cascade="all, delete-orphan")
    feed_events = db.relationship("FeedEvent", back_populates="profile", cascade="all, delete-orphan")


class NeeraList(db.Model):
    __tablename__ = "neera_list"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("user_profile.id"), nullable=False, index=True)
    category = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    visibility = db.Column(db.String(20), nullable=False, default="public")
    item_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    profile = db.relationship("UserProfile", back_populates="lists")
    items = db.relationship(
        "NeeraListItem",
        back_populates="neera_list",
        cascade="all, delete-orphan",
        order_by="NeeraListItem.position.asc()",
    )


class NeeraListItem(db.Model):
    __tablename__ = "neera_list_item"

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("neera_list.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=1)
    title = db.Column(db.String(220), nullable=False)
    creator_name = db.Column(db.String(180), nullable=False, default="")
    notes = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    neera_list = db.relationship("NeeraList", back_populates="items")


class Review(db.Model):
    __tablename__ = "review"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("user_profile.id"), nullable=False, index=True)
    work_id = db.Column(db.Integer, db.ForeignKey("neera_item.id"), nullable=True, index=True)
    category = db.Column(db.String(40), nullable=False)
    subject = db.Column(db.String(220), nullable=False)
    review_title = db.Column(db.String(220), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")
    rating = db.Column(db.Integer, nullable=False, default=4)
    spoiler = db.Column(db.Boolean, nullable=False, default=False)
    tags = db.Column(db.String(500), nullable=False, default="")
    visibility = db.Column(db.String(20), nullable=False, default="public")
    status = db.Column(db.String(20), nullable=False, default="published")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)

    profile = db.relationship("UserProfile", back_populates="reviews")
    work = db.relationship("NeeraItem", back_populates="reviews")


class NeeraNote(db.Model):
    __tablename__ = "neera_note"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("user_profile.id"), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    visibility = db.Column(db.String(20), nullable=False, default="public")
    status = db.Column(db.String(20), nullable=False, default="published")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    profile = db.relationship("UserProfile", back_populates="notes")


class NeeraItem(db.Model):
    __tablename__ = "neera_item"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False, index=True)
    creator_display_name = db.Column(db.String(180), nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    image_url = db.Column(db.String(500), nullable=False, default="")
    source_type = db.Column(db.String(20), nullable=False, default="seeded")
    source_id = db.Column(db.String(120), nullable=False, default="")
    is_user_submitted = db.Column(db.Boolean, nullable=False, default=False)
    metadata_confidence = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)
    reviews = db.relationship("Review", back_populates="work")
    book_metadata = db.relationship(
        "NeeraBookMetadata",
        back_populates="work",
        uselist=False,
        cascade="all, delete-orphan",
    )
    film_metadata = db.relationship(
        "NeeraFilmMetadata",
        back_populates="work",
        uselist=False,
        cascade="all, delete-orphan",
    )
    song_metadata = db.relationship(
        "NeeraSongMetadata",
        back_populates="work",
        uselist=False,
        cascade="all, delete-orphan",
    )
    art_metadata = db.relationship(
        "NeeraArtMetadata",
        back_populates="work",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def normalized_category(self):
        category_key = (self.category or "").strip().lower()
        mapping = {
            "book": "book",
            "books": "book",
            "film": "film",
            "films": "film",
            "movie": "film",
            "movies": "film",
            "song": "song",
            "songs": "song",
            "music": "song",
            "art": "art",
            "arts": "art",
            "artwork": "art",
            "artworks": "art",
        }
        return mapping.get(category_key, category_key)

    @property
    def category_metadata(self):
        mapping = {
            "book": self.book_metadata,
            "film": self.film_metadata,
            "song": self.song_metadata,
            "art": self.art_metadata,
        }
        return mapping.get(self.normalized_category)

    @property
    def creator_name(self):
        return self.creator_display_name

    @property
    def year_value(self):
        metadata = self.category_metadata
        if metadata is None:
            return None
        return getattr(metadata, "year", None)

    @property
    def length_label(self):
        metadata = self.category_metadata
        if metadata is None:
            return ""

        if self.normalized_category == "book" and metadata.pages:
            return f"{metadata.pages} pages"
        if self.normalized_category == "film" and metadata.runtime_minutes:
            return f"{metadata.runtime_minutes} min"
        if self.normalized_category == "song" and metadata.duration_seconds:
            minutes, seconds = divmod(metadata.duration_seconds, 60)
            return f"{minutes}m {seconds:02d}s"
        if self.normalized_category == "art":
            return metadata.medium or ""
        return ""

    @property
    def metadata_values(self):
        metadata = self.category_metadata
        if metadata is None:
            return {}

        if self.normalized_category == "book":
            return {
                "author": metadata.author,
                "year": metadata.year,
                "pages": metadata.pages,
                "publisher": metadata.publisher,
                "isbn": metadata.isbn,
                "language": metadata.language,
            }
        if self.normalized_category == "film":
            return {
                "director": metadata.director,
                "year": metadata.year,
                "runtime_minutes": metadata.runtime_minutes,
                "country": metadata.country,
                "language": metadata.language,
            }
        if self.normalized_category == "song":
            return {
                "artist": metadata.artist,
                "album": metadata.album,
                "year": metadata.year,
                "duration_seconds": metadata.duration_seconds,
            }
        if self.normalized_category == "art":
            return {
                "artist": metadata.artist,
                "year": metadata.year,
                "medium": metadata.medium,
                "movement": metadata.movement,
                "museum": metadata.museum,
            }
        return {}


class FeedEvent(db.Model):
    __tablename__ = "feed_event"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("user_profile.id"), nullable=False, index=True)
    target_type = db.Column(db.String(40), nullable=False)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)

    profile = db.relationship("UserProfile", back_populates="feed_events")


class NeeraBookMetadata(db.Model):
    __tablename__ = "neera_book_metadata"

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("neera_item.id"), nullable=False, unique=True, index=True)
    author = db.Column(db.String(180), nullable=False, default="")
    year = db.Column(db.Integer, nullable=True)
    pages = db.Column(db.Integer, nullable=True)
    publisher = db.Column(db.String(180), nullable=False, default="")
    isbn = db.Column(db.String(40), nullable=False, default="")
    language = db.Column(db.String(80), nullable=False, default="")

    work = db.relationship("NeeraItem", back_populates="book_metadata")


class NeeraFilmMetadata(db.Model):
    __tablename__ = "neera_film_metadata"

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("neera_item.id"), nullable=False, unique=True, index=True)
    director = db.Column(db.String(180), nullable=False, default="")
    year = db.Column(db.Integer, nullable=True)
    runtime_minutes = db.Column(db.Integer, nullable=True)
    country = db.Column(db.String(120), nullable=False, default="")
    language = db.Column(db.String(80), nullable=False, default="")

    work = db.relationship("NeeraItem", back_populates="film_metadata")


class NeeraSongMetadata(db.Model):
    __tablename__ = "neera_song_metadata"

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("neera_item.id"), nullable=False, unique=True, index=True)
    artist = db.Column(db.String(180), nullable=False, default="")
    album = db.Column(db.String(220), nullable=False, default="")
    year = db.Column(db.Integer, nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)

    work = db.relationship("NeeraItem", back_populates="song_metadata")


class NeeraArtMetadata(db.Model):
    __tablename__ = "neera_art_metadata"

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("neera_item.id"), nullable=False, unique=True, index=True)
    artist = db.Column(db.String(180), nullable=False, default="")
    year = db.Column(db.Integer, nullable=True)
    medium = db.Column(db.String(180), nullable=False, default="")
    movement = db.Column(db.String(180), nullable=False, default="")
    museum = db.Column(db.String(220), nullable=False, default="")

    work = db.relationship("NeeraItem", back_populates="art_metadata")
