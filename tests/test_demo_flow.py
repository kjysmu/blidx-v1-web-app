from fastapi.testclient import TestClient

from app.core.config import settings
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


def test_seed_test_scenario_makes_app_immediately_testable():
    response = client.post("/api/seed-test-scenario")

    assert response.status_code == 200
    state = response.json()
    assert state["test_scenario"]["loaded"] is True
    assert state["profile"]["first_name"] == "Malia"
    assert state["profile"]["company_name"] == "HeyJuni"
    assert len(state["content_bank"]) == 3
    assert state["posts"] == []

    draft_response = client.post(
        "/api/drafts",
        json={"topic": state["test_scenario"]["next_prompt"], "source": "tester_scenario"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "pending"
    assert draft["generation_provider"] in {"template", f"Anthropic {settings.ANTHROPIC_MODEL}"}
    assert "is not mainly a content problem" not in draft["content"]

    client.post("/api/reset")


def test_mira_chat_creates_a_draft_and_records_messages():
    client.post("/api/seed-test-scenario")

    response = client.post(
        "/api/chat/message",
        json={"message": "Draft a post about human connection versus AI in mental health"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_created" in payload["actions"]
    assert payload["post"]["status"] == "pending"
    assert "human" in payload["post"]["content"].lower()
    assert len(payload["state"]["messages"]) >= 3
    assert payload["state"]["messages"][-2]["role"] == "user"
    assert payload["state"]["messages"][-1]["role"] == "mira"

    client.post("/api/reset")


def test_mira_redirects_off_topic_chat_without_creating_draft():
    client.post("/api/reset")

    response = client.post(
        "/api/chat/message",
        json={"message": "What is the weather today?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"] == ["redirect"]
    assert payload["post"] is None
    assert payload["state"]["posts"] == []

    client.post("/api/reset")


def test_publish_uses_manual_fallback_without_linkedin_token():
    client.post("/api/seed-test-scenario")
    draft = client.post(
        "/api/chat/message",
        json={"message": "Draft a post about human connection versus AI in mental health"},
    ).json()["post"]

    response = client.post(f"/api/drafts/{draft['id']}/publish")

    assert response.status_code == 200
    data = response.json()
    assert data["published"] is False
    assert data["mode"] == "manual_fallback"
    assert data["fallback_url"] == "https://www.linkedin.com/feed/"

    client.post("/api/reset")


def test_mira_fallback_varies_chat_replies_and_offers_angles():
    client.post("/api/seed-test-scenario")

    first = client.post(
        "/api/chat/message",
        json={"message": "What should I post about today?"},
    ).json()
    second = client.post(
        "/api/chat/message",
        json={"message": "Give me angles from the AI event"},
    ).json()

    old_repeated_line = "I have 3 Content Bank entries to work from"
    assert old_repeated_line not in first["reply"]
    assert old_repeated_line not in second["reply"]
    assert first["reply"] != second["reply"]
    assert "angle" in second["reply"].lower()

    client.post("/api/reset")


def test_mira_understands_draft_follow_up_after_angle_prompt():
    client.post("/api/seed-test-scenario")

    client.post(
        "/api/chat/message",
        json={"message": "Give me angles from the AI event"},
    )
    response = client.post(
        "/api/chat/message",
        json={"message": "yes please"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_created" in payload["actions"]
    assert payload["post"]["status"] == "pending"

    client.post("/api/reset")
