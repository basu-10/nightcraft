import time
import uuid

from app import create_app


app = create_app()
client = app.test_client()

email = f"dbg_{uuid.uuid4().hex[:8]}@e.com"
client.post("/auth/register", json={"email": email, "password": "Password123!"})
ws = client.post(
    "/api/workspaces",
    json={"name": "w", "workspace_type": "react", "tool_ids": ["web_search"]},
).get_json()
session = client.post(
    f"/api/workspaces/{ws['id']}/sessions",
    json={"title": "t"},
).get_json()
run = client.post(
    f"/api/sessions/{session['id']}/runs",
    json={"query": "hello"},
).get_json()

time.sleep(4)
print(client.get(f"/api/runs/{run['id']}").get_json())
print(client.get(f"/api/runs/{run['id']}/events").get_json())
