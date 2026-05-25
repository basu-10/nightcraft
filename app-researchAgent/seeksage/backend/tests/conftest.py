"""
conftest.py — shared pytest fixtures for the SeekSage backend test suite.

Isolation strategy
------------------
* Tests run against a dedicated PostgreSQL test database set by TEST_DATABASE_URL.
* The Flask app is created once per session with TESTING=True.
* A seeded test user + workspace + ConnectionProfile are created per-session.

Fixtures available to all tests
---------------------------------
app         Flask app (session scope)
db_session  SQLAlchemy scoped session (function scope, rolls back after each test)
client      Flask test client (function scope)
auth_client Flask test client already logged-in as the test user (function scope)
test_user   the User ORM object
test_ws     the Workspace ORM object
or_profile  the OpenRouter ConnectionProfile ORM object (uses key from .env.test)
"""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml
from dotenv import load_dotenv

# ── Test environment setup — MUST happen before any 'from app import ...' ─────
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is required for PostgreSQL-backed tests.", allow_module_level=True)

# Set this at module-import time so Config class attributes (evaluated at
# class-definition time) pick up test values.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TESTING"] = "1"
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("WERKZEUG_RUN_MAIN", "false")

# Load .env.test before anything else so OPENROUTER_API_KEY etc. are available
_env_test = os.path.join(os.path.dirname(__file__), ".env.test")
if os.path.exists(_env_test):
    load_dotenv(_env_test, override=True)


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create a test Flask app backed by a temporary in-memory DB."""
    # DATABASE_URL and TESTING are already set at module level above,
    # before any app.* module was imported.
    from app import create_app

    _app = create_app()
    _app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        LOGIN_DISABLED=False,
    )

    # Re-create tables for the in-memory DB
    with _app.app_context():
        from app.extensions import db as _db
        _db.create_all()

    yield _app


@pytest.fixture(scope="session")
def _db_obj(app):
    from app.extensions import db as _db
    return _db


# ── Per-test DB rollback ───────────────────────────────────────────────────────

@pytest.fixture()
def db_session(app, _db_obj):
    """
    Wraps each test in a transaction that is rolled back at the end,
    keeping the DB clean between tests without recreating tables.
    """
    with app.app_context():
        connection = _db_obj.engine.connect()
        transaction = connection.begin()
        # Bind the session to this connection so all ORM ops use it
        _db_obj.session.configure(bind=connection)
        yield _db_obj.session
        _db_obj.session.remove()
        transaction.rollback()
        connection.close()
        # IMPORTANT: restore the session to use the engine directly so that
        # tests which don't request db_session still get a healthy session.
        _db_obj.session.configure(bind=_db_obj.engine)


# ── Test user / workspace / profile ──────────────────────────────────────────

@pytest.fixture(scope="session")
def test_user(app, _db_obj):
    with app.app_context():
        from app.models import User
        user = User(email="test@chotu.test", is_admin=True, active=True)
        user.set_password("testpassword123")
        _db_obj.session.add(user)
        _db_obj.session.commit()
        # Detach and re-fetch to avoid cross-session issues
        uid = user.id
    return uid


@pytest.fixture(scope="session")
def test_ws(app, _db_obj, test_user):
    with app.app_context():
        from app.models import Workspace
        ws = Workspace(
            user_id=test_user,
            name="Test Workspace",
            color="#4A90D9",
            workspace_type="react",
            tool_ids=["web_search", "wiki_search", "visit_url"],
        )
        _db_obj.session.add(ws)
        _db_obj.session.commit()
        wid = ws.id
    return wid


@pytest.fixture(scope="session")
def or_profile(app, _db_obj, test_user, test_ws):
    """Create an OpenRouter ConnectionProfile using the key from .env.test."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    with app.app_context():
        from app.models import ConnectionProfile, Workspace
        profile = ConnectionProfile(
            user_id=test_user,
            name="Test OpenRouter",
            provider="openrouter",
            is_active=True,
            settings={
                "api_key": api_key,
                "agent_model": os.environ.get("TEST_AGENT_MODEL", "openai/gpt-4o-mini"),
                "agent_model_fallback": os.environ.get("TEST_FALLBACK_MODEL", "openai/gpt-3.5-turbo"),
            },
        )
        _db_obj.session.add(profile)
        _db_obj.session.flush()

        # Link workspace to this profile
        ws = Workspace.query.get(test_ws)
        ws.profile_id = profile.id
        _db_obj.session.commit()
        pid = profile.id
    return pid


# ── Flask test clients ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def auth_client(app, test_user):
    """Test client pre-logged-in as the test user."""
    with app.test_client() as c:
        with app.app_context():
            from app.models import User
            from flask_login import login_user
            user = User.query.get(test_user)
            with c.session_transaction() as sess:
                # Use Flask-Login's test helpers
                pass
        # POST /auth/login to establish the session cookie
        rv = c.post(
            "/auth/login",
            json={"email": "test@chotu.test", "password": "testpassword123"},
        )
        assert rv.status_code == 200, f"auth_client login failed: {rv.data}"
        yield c


# ── YAML fixture loader ───────────────────────────────────────────────────────

def load_yaml_cases(filename: str) -> list[dict]:
    """Load test cases from tests/fixtures/<filename>."""
    path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("cases", []) if isinstance(data, dict) else data


# ── Markers ───────────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "live: tests that call real external APIs")
    config.addinivalue_line("markers", "slow: tests that take more than a few seconds")
    config.addinivalue_line("markers", "unit: fast isolated unit tests")
    config.addinivalue_line("markers", "integration: tests requiring the full app context")
