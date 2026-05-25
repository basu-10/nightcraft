import json
import os
import time

from app import create_app


def run():
    app = create_app()
    app.testing = True
    client = app.test_client()

    email = f"smoke_{int(time.time())}@example.com"
    password = "Password123!"

    reg = client.post("/auth/register", json={"email": email, "password": password})
    assert reg.status_code in (200, 201), reg.get_data(as_text=True)

    settings = {
        "or_api_key": os.getenv("OPENROUTER_API_KEY", ""),
        "agent": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "agent_fallback": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "code": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "code_fallback": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "summarization": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
        "summarization_fallback": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
    }

    profile_res = client.post(
        "/api/profiles",
        json={
            "name": "OpenRouter Advanced",
            "provider": "advanced",
            "settings": settings,
            "is_active": True,
        },
    )
    assert profile_res.status_code == 201, profile_res.get_data(as_text=True)
    profile = profile_res.get_json()

    tool_settings_res = client.patch(
        "/api/settings/tools",
        json={
            "react_agent": {"max_steps": 4},
            "web_search": {"default_max_results": 2, "max_results_limit": 4},
        },
    )
    assert tool_settings_res.status_code == 200, tool_settings_res.get_data(as_text=True)

    ws_res = client.post(
        "/api/workspaces",
        json={
            "name": "Smoke Workspace",
            "workspace_type": "react",
            "profile_id": profile["id"],
            "tool_ids": [
                "web_search",
                "wiki_search",
                "visit_url",
                "news_search",
                "youtube_transcript",
                "arxiv_search",
                "save_text",
                "create_slides",
            ],
        },
    )
    assert ws_res.status_code == 201, ws_res.get_data(as_text=True)
    workspace = ws_res.get_json()

    session_res = client.post(f"/api/workspaces/{workspace['id']}/sessions", json={"title": "Smoke Chat"})
    assert session_res.status_code == 201, session_res.get_data(as_text=True)
    session = session_res.get_json()

    run_res = client.post(
        f"/api/sessions/{session['id']}/runs",
        json={"query": "Say hello in one sentence without using tools."},
    )
    assert run_res.status_code == 201, run_res.get_data(as_text=True)
    run = run_res.get_json()

    status = run["status"]
    for _ in range(90):
        current = client.get(f"/api/runs/{run['id']}")
        assert current.status_code == 200, current.get_data(as_text=True)
        status = current.get_json().get("status")
        if status in ("done", "error"):
            break
        time.sleep(1)

    events_res = client.get(f"/api/runs/{run['id']}/events")
    assert events_res.status_code == 200, events_res.get_data(as_text=True)
    events = events_res.get_json()

    messages_res = client.get(f"/api/sessions/{session['id']}/messages")
    assert messages_res.status_code == 200, messages_res.get_data(as_text=True)
    messages = messages_res.get_json()

    print("SMOKE SUMMARY")
    print(json.dumps({
        "run_status": status,
        "event_count": len(events),
        "message_count": len(messages),
        "assistant_messages": [m for m in messages if m.get("role") == "assistant"],
    }, indent=2))


if __name__ == "__main__":
    run()
