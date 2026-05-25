"""
test_api.py — Integration tests for all Flask API endpoints.

Strategy
--------
* All requests go through the Flask test client (no real HTTP).
* Authenticated tests use the ``auth_client`` fixture (session cookie already set).
* Test cases are driven from fixtures/api_cases.yaml for the YAML-driven suite,
  plus explicit test methods for CRUD flows that need state (create → read → delete).
* The activity log is used to tag each test action for traceability.
"""

from __future__ import annotations

import os
import time

import pytest
import yaml


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_api_cases(section: str) -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "fixtures", "api_cases.yaml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (data or {}).get(section, {}).get("cases", [])


def _actlog(case_id: str, method: str, path: str, status: int, duration_ms: int, passed: bool):
    from app.core import activity_log as actlog
    actlog.log(
        "test_api",
        {
            "case_id": case_id,
            "method": method,
            "path": path,
            "status": status,
            "passed": passed,
            "duration_ms": duration_ms,
        },
        user_id="test-harness",
        run_id=f"test:{case_id}",
    )


def _do_request(client, method: str, path: str, body: dict | None = None):
    t0 = time.monotonic()
    fn = getattr(client, method.lower())
    rv = fn(path, json=body) if body else fn(path)
    duration_ms = int((time.monotonic() - t0) * 1000)
    return rv, duration_ms


# ── Auth tests ─────────────────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.integration
    def test_me_authenticated(self, auth_client):
        """GET /auth/me returns 200 with authenticated user info when logged in."""
        rv, ms = _do_request(auth_client, "GET", "/auth/me")
        _actlog("auth_me", "GET", "/auth/me", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["authenticated"] is True
        assert "id" in data["user"] and "email" in data["user"]

    @pytest.mark.integration
    def test_me_unauthenticated(self, client):
        """GET /auth/me returns 200 with authenticated=False when not logged in."""
        rv, ms = _do_request(client, "GET", "/auth/me")
        _actlog("auth_me_unauth", "GET", "/auth/me", rv.status_code, ms, True)
        assert rv.status_code == 200
        assert rv.get_json()["authenticated"] is False

    @pytest.mark.integration
    def test_login_wrong_password(self, client):
        rv, ms = _do_request(client, "POST", "/auth/login",
                             {"email": "test@chotu.test", "password": "wrongpassword"})
        _actlog("auth_bad_pwd", "POST", "/auth/login", rv.status_code, ms, rv.status_code == 401)
        assert rv.status_code == 401

    @pytest.mark.integration
    def test_login_unknown_user(self, client):
        rv, ms = _do_request(client, "POST", "/auth/login",
                             {"email": "nobody@chotu.test", "password": "pass"})
        assert rv.status_code == 401

    @pytest.mark.integration
    def test_change_password_roundtrip(self, auth_client):
        rv, ms = _do_request(
            auth_client, "POST", "/auth/change-password",
            {"current_password": "testpassword123", "new_password": "testpassword123"},
        )
        _actlog("auth_change_pwd", "POST", "/auth/change-password", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200


# ── Workspace CRUD ─────────────────────────────────────────────────────────────

class TestWorkspaces:
    @pytest.mark.integration
    def test_list_workspaces(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/api/workspaces")
        _actlog("ws_list", "GET", "/api/workspaces", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    @pytest.mark.integration
    def test_create_and_get_workspace(self, auth_client):
        # Create
        rv, ms = _do_request(auth_client, "POST", "/api/workspaces", {
            "name": "CRUD Test WS",
            "color": "#50C878",
            "workspace_type": "react",
            "tool_ids": ["web_search"],
        })
        _actlog("ws_create", "POST", "/api/workspaces", rv.status_code, ms, rv.status_code == 201)
        assert rv.status_code == 201
        ws = rv.get_json()
        assert ws["name"] == "CRUD Test WS"
        ws_id = ws["id"]

        # Get
        rv2, _ = _do_request(auth_client, "GET", f"/api/workspaces/{ws_id}")
        assert rv2.status_code == 200
        assert rv2.get_json()["id"] == ws_id

        # Delete
        rv3, _ = _do_request(auth_client, "DELETE", f"/api/workspaces/{ws_id}")
        assert rv3.status_code in (200, 204)

    @pytest.mark.integration
    def test_patch_workspace(self, auth_client, test_ws):
        rv, ms = _do_request(auth_client, "PATCH", f"/api/workspaces/{test_ws}", {
            "name": "Updated Name"
        })
        _actlog("ws_patch", "PATCH", f"/api/workspaces/{test_ws}", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        assert rv.get_json()["name"] == "Updated Name"

        # Restore
        auth_client.patch(f"/api/workspaces/{test_ws}", json={"name": "Test Workspace"})


# ── Sessions ───────────────────────────────────────────────────────────────────

class TestSessions:
    @pytest.mark.integration
    def test_create_list_delete_session(self, auth_client, test_ws):
        # Create
        rv, ms = _do_request(auth_client, "POST", f"/api/workspaces/{test_ws}/sessions", {
            "title": "Test Session"
        })
        _actlog("session_create", "POST", f"/api/workspaces/{test_ws}/sessions", rv.status_code, ms, rv.status_code == 201)
        assert rv.status_code == 201
        sess = rv.get_json()
        assert sess["title"] == "Test Session"
        sess_id = sess["id"]

        # List
        rv2, _ = _do_request(auth_client, "GET", f"/api/workspaces/{test_ws}/sessions")
        assert rv2.status_code == 200
        ids = [s["id"] for s in rv2.get_json()]
        assert sess_id in ids

        # Patch title
        rv3, _ = _do_request(auth_client, "PATCH", f"/api/sessions/{sess_id}", {
            "title": "Renamed Session"
        })
        assert rv3.status_code == 200

        # Delete
        rv4, _ = _do_request(auth_client, "DELETE", f"/api/sessions/{sess_id}")
        assert rv4.status_code in (200, 204)

    @pytest.mark.integration
    def test_session_messages(self, auth_client, test_ws):
        # Create a session then check messages list
        rv, _ = _do_request(auth_client, "POST", f"/api/workspaces/{test_ws}/sessions", {
            "title": "Msg Test Session"
        })
        sess_id = rv.get_json()["id"]
        rv2, _ = _do_request(auth_client, "GET", f"/api/sessions/{sess_id}/messages")
        assert rv2.status_code == 200
        assert isinstance(rv2.get_json(), list)
        # Cleanup
        auth_client.delete(f"/api/sessions/{sess_id}")


# ── Profiles ───────────────────────────────────────────────────────────────────

class TestProfiles:
    @pytest.mark.integration
    def test_list_profiles(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/api/profiles")
        _actlog("profile_list", "GET", "/api/profiles", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), list)

    @pytest.mark.integration
    def test_create_and_delete_profile(self, auth_client):
        rv, ms = _do_request(auth_client, "POST", "/api/profiles", {
            "name": "Temp Profile",
            "provider": "openrouter",
            "settings": {"api_key": "sk-test", "agent_model": "openai/gpt-4o-mini"},
        })
        _actlog("profile_create", "POST", "/api/profiles", rv.status_code, ms, rv.status_code == 201)
        assert rv.status_code == 201
        pid = rv.get_json()["id"]

        rv2, _ = _do_request(auth_client, "DELETE", f"/api/profiles/{pid}")
        assert rv2.status_code in (200, 204)

    @pytest.mark.integration
    def test_activate_profile(self, auth_client, or_profile):
        rv, ms = _do_request(auth_client, "POST", f"/api/profiles/{or_profile}/activate")
        _actlog("profile_activate", "POST", f"/api/profiles/{or_profile}/activate", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        assert rv.get_json()["is_active"] is True


# ── Tool settings ──────────────────────────────────────────────────────────────

class TestToolSettings:
    @pytest.mark.integration
    def test_get_tool_settings(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/api/settings/tools")
        _actlog("tool_settings_get", "GET", "/api/settings/tools", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        assert isinstance(rv.get_json(), dict)

    @pytest.mark.integration
    def test_update_tool_settings(self, auth_client):
        rv, ms = _do_request(auth_client, "PATCH", "/api/settings/tools", {
            "web_search": {"default_max_results": 5, "max_results_limit": 10}
        })
        _actlog("tool_settings_patch", "PATCH", "/api/settings/tools", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200


# ── Admin endpoints ────────────────────────────────────────────────────────────

class TestAdmin:
    @pytest.mark.integration
    def test_admin_stats(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/admin/stats")
        _actlog("admin_stats", "GET", "/admin/stats", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        data = rv.get_json()
        assert "user_count" in data and "run_count" in data

    @pytest.mark.integration
    def test_admin_list_users(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/admin/users")
        _actlog("admin_users", "GET", "/admin/users", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        users = rv.get_json()
        assert isinstance(users, list)
        emails = [u["email"] for u in users]
        assert "test@chotu.test" in emails

    @pytest.mark.integration
    def test_admin_activity_logs(self, auth_client):
        rv, ms = _do_request(auth_client, "GET", "/admin/activity_logs?limit=5")
        _actlog("admin_actlog", "GET", "/admin/activity_logs", rv.status_code, ms, rv.status_code == 200)
        assert rv.status_code == 200
        data = rv.get_json()
        assert "total" in data and "rows" in data

    @pytest.mark.integration
    def test_admin_activity_logs_filtered_by_user(self, auth_client, test_user):
        rv, ms = _do_request(auth_client, "GET", f"/admin/activity_logs?user_id={test_user}&limit=10")
        assert rv.status_code == 200
        data = rv.get_json()
        for row in data["rows"]:
            assert row["user_id"] == test_user

    @pytest.mark.integration
    def test_admin_create_and_delete_user(self, auth_client):
        # Create
        rv, ms = _do_request(auth_client, "POST", "/admin/users", {
            "email": "temp-admin-test@chotu.test",
            "password": "TempPass123!",
            "is_admin": False,
        })
        _actlog("admin_create_user", "POST", "/admin/users", rv.status_code, ms, rv.status_code == 201)
        assert rv.status_code == 201
        uid = rv.get_json()["id"]

        # Delete
        rv2, _ = _do_request(auth_client, "DELETE", f"/admin/users/{uid}")
        assert rv2.status_code in (200, 204)


# ── Health check ───────────────────────────────────────────────────────────────

class TestHealth:
    @pytest.mark.unit
    def test_health(self, client):
        rv, _ = _do_request(client, "GET", "/api/health")
        assert rv.status_code == 200
        assert rv.get_json().get("status") == "ok"
