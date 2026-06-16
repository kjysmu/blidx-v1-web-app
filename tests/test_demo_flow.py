from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_complete_local_web_app_flow():
    client.post("/api/reset")

    profile_response = client.put(
        "/api/profile",
        json={
            "first_name": "Jae",
            "company_name": "Blidx",
            "audience": ["Founders"],
            "tone": "Bold & opinionated",
        },
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["company_name"] == "Blidx"

    memory_response = client.post(
        "/api/content-bank",
        json={
            "category": "milestones",
            "raw_text": "We launched the first local Blidx workflow and learned fast.",
        },
    )
    assert memory_response.status_code == 200
    assert memory_response.json()["freshness"] == "fresh"

    draft_response = client.post(
        "/api/drafts",
        json={"topic": "why founder content needs workflow ownership"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "pending"
    assert "launched the first local Blidx workflow" in draft["content"]

    edit_response = client.post(
        f"/api/drafts/{draft['id']}/edit",
        json={"instructions": "Make it more personal"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["version"] == 2

    approve_response = client.post(
        f"/api/drafts/{draft['id']}/approve",
        json={"schedule_type": "best_time"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "scheduled"
    assert approve_response.json()["scheduled_at"] is not None

    state = client.get("/api/state").json()
    assert len(state["content_bank"]) == 1
    assert state["posts"][0]["status"] == "scheduled"

    client.post("/api/reset")
