from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


# Spec relation types (P1 provenance vocabulary). Only these are permitted.
RELATION_TYPES = [
    "derived_from",
    "version_of",
    "references",
    "cites",
    "supports",
    "contradicts",
    "contains",
    "depends_on",
    "generated_by",
]

# Asset content types Alfred understands.
ASSET_TYPE_REPORT = "report"
ASSET_TYPE_DOCUMENT = "document"


class LocalCredential(UserMixin, db.Model):
    __tablename__ = "local_credential"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

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
            bio="Asking Alfred questions and building a personal library.",
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
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Asset(db.Model):
    """Immutable library artifact. Identity = content_hash (dedupe on ingest)."""

    __tablename__ = "asset"

    id = db.Column(db.Integer, primary_key=True)
    content_hash = db.Column(db.String(64), nullable=False, index=True)
    content_type = db.Column(db.String(40), nullable=False, default=ASSET_TYPE_DOCUMENT)
    storage_ref = db.Column(db.String(512), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False, default="application/octet-stream")
    title = db.Column(db.String(300), nullable=False, default="Untitled")
    metadata_json = db.Column(db.Text, nullable=False, default="{}")
    lineage_json = db.Column(db.Text, nullable=False, default="{}")
    user_id = db.Column(db.String(100), nullable=False, index=True)
    workspace_id = db.Column(db.String(100), nullable=True)  # deferred: nullable/unused (P3 #8)
    status = db.Column(db.String(20), nullable=False, default="ready")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("content_hash", "user_id", name="uq_asset_hash_user"),)

    @property
    def asset_metadata(self):
        import json

        try:
            return json.loads(self.metadata_json or "{}")
        except (ValueError, TypeError):
            return {}

    @property
    def lineage(self):
        import json

        try:
            return json.loads(self.lineage_json or "{}")
        except (ValueError, TypeError):
            return {}


class AssetChunk(db.Model):
    """Extracted text chunk of an Asset. Source of truth for embeddings + edits."""

    __tablename__ = "asset_chunk"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    token_count = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("asset_id", "chunk_index", name="uq_chunk_asset_index"),)


class AssetRelation(db.Model):
    __tablename__ = "asset_relation"

    id = db.Column(db.Integer, primary_key=True)
    from_id = db.Column(db.Integer, db.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True)
    to_id = db.Column(db.Integer, db.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = db.Column(db.String(30), nullable=False)

    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "relation_type", name="uq_relation"),
        Index("ix_relation_type", "relation_type"),
    )


class Evidence(db.Model):
    """Mandatory provenance for any generated artifact or claim (P4)."""

    __tablename__ = "evidence"

    id = db.Column(db.Integer, primary_key=True)
    source_asset_ids = db.Column(db.Text, nullable=False, default="[]")
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    run_id = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def sources(self):
        import json

        try:
            return json.loads(self.source_asset_ids or "[]")
        except (ValueError, TypeError):
            return []

    @property
    def payload(self):
        import json

        try:
            return json.loads(self.payload_json or "{}")
        except (ValueError, TypeError):
            return {}


def assert_derivation_has_sources(evidence: "Evidence | None"):
    """Boundary validator (P2 #4): a derived artifact MUST cite sources.

    Rejects with ``ValueError`` when the lineage claims derivation but the
    Evidence carries no source asset ids. Call this on the artifact write path.
    """
    if evidence is None:
        raise ValueError("derived artifact requires provenance Evidence (P4).")
    if not evidence.sources:
        raise ValueError("derived artifact requires non-empty Evidence.sources (P4).")
    return True


class AgentRun(db.Model):
    __tablename__ = "agent_run"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.String(100), nullable=False, index=True)
    workspace_id = db.Column(db.String(100), nullable=True)  # deferred: nullable/unused (P3 #8)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    goal = db.Column(db.Text, nullable=False, default="")
    plan_json = db.Column(db.Text, nullable=False, default="{}")

    # Runtime policies (P1 #2): bounds enforced by the executor ReAct loop.
    # Nullable => no bound (unbounded) when not set.
    max_runtime_seconds = db.Column(db.Integer, nullable=True)
    idle_timeout_seconds = db.Column(db.Integer, nullable=True)
    token_budget = db.Column(db.Integer, nullable=True)
    cost_budget_usd = db.Column(db.Float, nullable=True)

    # Determinism / provenance provenance (P2 #13 Capability Versioning).
    capability = db.Column(db.String(80), nullable=True)
    capability_version = db.Column(db.String(40), nullable=True)
    manifest_hash = db.Column(db.String(64), nullable=True)

    # Artifact Version Pinning (P2 #14): input is pinned at RESOLUTION time, not
    # compile time. run_input_hash captures the referenced asset ids + their
    # content hashes as they existed when the run started, so a user edit to a
    # referenced asset after compile does not change the executed input.
    run_input_hash = db.Column(db.String(64), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="queued")
    error = db.Column(db.Text, nullable=True)

    # Live runtime accounting, refreshed by the executor. last_activity_at drives
    # the idle-timeout check; tokens_used / cost_usd feed the budgets.
    started_at = db.Column(db.DateTime, nullable=True)
    last_activity_at = db.Column(db.DateTime, nullable=True)
    tokens_used = db.Column(db.Integer, nullable=False, default=0)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @property
    def plan(self):
        import json

        try:
            return json.loads(self.plan_json or "{}")
        except (ValueError, TypeError):
            return {}


class RunEvent(db.Model):
    __tablename__ = "run_event"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.String(100), nullable=False, index=True)
    seq = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    payload_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_event_seq"),)

    @property
    def payload(self):
        import json

        try:
            return json.loads(self.payload_json or "{}")
        except (ValueError, TypeError):
            return {}


class ChatSession(db.Model):
    __tablename__ = "chat_session"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=lambda: __import__("uuid").uuid4().hex)
    user_id = db.Column(db.String(100), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False, default="New conversation")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Message(db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.String(100), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    referenced_asset_ids = db.Column(db.Text, nullable=False, default="[]")
    run_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def references(self):
        import json

        try:
            return json.loads(self.referenced_asset_ids or "[]")
        except (ValueError, TypeError):
            return []


class AssetEmbedding(db.Model):
    """pgvector embedding per AssetChunk. Model id stored per row for cheap re-index."""

    __tablename__ = "asset_embedding"

    id = db.Column(db.Integer, primary_key=True)
    chunk_id = db.Column(
        db.Integer, db.ForeignKey("asset_chunk.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id", ondelete="CASCADE"), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    embedding = db.Column(db.Text, nullable=False)  # stored as JSON list for driver-agnostic pgvector

    __table_args__ = (UniqueConstraint("chunk_id", "model", name="uq_chunk_model"),)


class AppSetting(db.Model):
    __tablename__ = "app_setting"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    encrypted = db.Column(db.Boolean, nullable=False, default=False)
