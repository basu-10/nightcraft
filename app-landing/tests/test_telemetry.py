"""Integration tests for telemetry API."""
from unittest.mock import patch

from landing import create_app


def _client():
    app = create_app()
    app.config.update(
        TESTING=True,
        TELEMETRY_DATABASE_URL="",
    )
    return app.test_client()


def test_telemetry_endpoint_accepts_batched_events():
    client = _client()

    payload = {
        "events": [
            {
                "event_id": "evt-1",
                "event_type": "page_view",
                "session_id": "session-abc",
                "url": "https://example.com/",
                "referrer": "https://google.com/",
                "properties": {"title": "Home"},
            }
        ]
    }

    response = client.post("/api/telemetry/v1/events", json=payload)

    assert response.status_code == 207
    body = response.get_json()
    assert body["accepted"] == 1
    assert body["rejected"] == 0


def test_telemetry_endpoint_rejects_invalid_payload():
    client = _client()

    response = client.post("/api/telemetry/v1/events", json={"events": "not-a-list"})
    assert response.status_code == 207


def test_telemetry_endpoint_deduplicates_events():
    client = _client()

    event = {
        "event_id": "evt-dup",
        "event_type": "page_view",
        "session_id": "session-xyz",
        "url": "https://example.com/",
    }

    response1 = client.post("/api/telemetry/v1/events", json={"events": [event]})
    response2 = client.post("/api/telemetry/v1/events", json={"events": [event]})

    assert response1.status_code == 207
    assert response1.get_json()["accepted"] == 1
    assert response2.status_code == 207
    assert response2.get_json()["accepted"] == 0


def test_telemetry_endpoint_filters_invalid_event_types():
    client = _client()

    payload = {
        "events": [
            {
                "event_id": "evt-bad",
                "event_type": "unknown_type",
                "session_id": "session-1",
                "url": "https://example.com/",
            }
        ]
    }

    response = client.post("/api/telemetry/v1/events", json=payload)
    assert response.status_code == 207
    assert response.get_json()["accepted"] == 0


def test_telemetry_endpoint_rate_limits_when_configured():
    app = create_app()
    app.config.update(
        TESTING=True,
        TELEMETRY_RATE_LIMIT="2",
    )
    client = app.test_client()

    event = {
        "event_id": "evt-ratelimit",
        "event_type": "page_view",
        "session_id": "session-rl",
        "url": "https://example.com/",
    }

    for i in range(3):
        event["event_id"] = "evt-ratelimit-" + str(i)
        response = client.post("/api/telemetry/v1/events", json={"events": [event]})

    assert response.status_code == 429
