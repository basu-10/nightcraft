from datetime import datetime
from uuid import uuid4

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def _uuid() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    workspaces = db.relationship("Workspace", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Workspace(TimestampMixin, db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    color = db.Column(db.String(16), nullable=False, default="#4A90D9")
    workspace_type = db.Column(db.String(32), nullable=False, default="react")
    tool_ids = db.Column(db.JSON, nullable=False, default=list)
    profile_id = db.Column(db.String(36), nullable=True, index=True)

    sessions = db.relationship("ChatSession", backref="workspace", lazy=True, cascade="all, delete-orphan")


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    memory_text = db.Column(db.Text, nullable=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)

    sessions = db.relationship("ChatSession", backref="project", lazy="dynamic")


class ChatSession(TimestampMixin, db.Model):
    __tablename__ = "chat_sessions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = db.Column(
        db.String(36),
        db.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = db.Column(
        db.String(36),
        db.ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False, default="New Chat")
    thread_id = db.Column(db.String(64), nullable=False, unique=True, default=_uuid)
    archived = db.Column(db.Boolean, nullable=False, default=False)

    messages = db.relationship("Message", backref="chat_session", lazy=True, cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(24), nullable=False)  # user, assistant, tool, system
    content = db.Column(db.Text, nullable=False)
    tool_steps = db.Column(db.JSON, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    checkpoint_id = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class Note(TimestampMixin, db.Model):
    __tablename__ = "notes"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = db.Column(db.String(36), db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    chat_session_id = db.Column(db.String(36), db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    tags = db.Column(db.JSON, nullable=False, default=list)


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(40), nullable=False, default="system", index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False, default="")
    read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    metadata_json = db.Column(db.JSON, nullable=True)


class SessionFile(TimestampMixin, db.Model):
    __tablename__ = "session_files"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = db.Column(db.String(36), db.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_session_id = db.Column(db.String(36), db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(24), nullable=False, default="uploaded", index=True)
    storage_path = db.Column(db.String(1024), nullable=False)
    mime_type = db.Column(db.String(255), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("user_id", "chat_session_id", "storage_path", name="uq_session_file_path"),
    )


class ConnectionProfile(TimestampMixin, db.Model):
    __tablename__ = "connection_profiles"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    provider = db.Column(db.String(32), nullable=False, default="lm_studio")
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    settings = db.Column(db.JSON, nullable=False, default=dict)


class AgentRun(TimestampMixin, db.Model):
    __tablename__ = "agent_runs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = db.Column(
        db.String(36),
        db.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chat_session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_type = db.Column(db.String(24), nullable=False, default="react")
    status = db.Column(db.String(24), nullable=False, default="queued")
    query_text = db.Column(db.Text, nullable=False)
    final_answer = db.Column(db.Text, nullable=True)
    error_text = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)


class RunEvent(db.Model):
    __tablename__ = "run_events"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    run_id = db.Column(
        db.String(36),
        db.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint("run_id", "seq", name="uq_run_event_seq"),
    )


class UserPreference(TimestampMixin, db.Model):
    __tablename__ = "user_preferences"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = db.Column(db.String(120), nullable=False)
    value_json = db.Column(db.JSON, nullable=False, default=dict)

    __table_args__ = (
        db.UniqueConstraint("user_id", "key", name="uq_user_pref_key"),
    )
