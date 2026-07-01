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
    assert first["post"] is None
    assert "memory_saved" not in first["actions"]
    assert len(first["state"]["content_bank"]) == 3
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
    assert payload["post"]["title"] != "Draft it"
    assert "What does draft it" not in payload["post"]["content"]

    client.post("/api/reset")


def test_mira_drafts_from_latest_memory_phrase():
    client.post("/api/reset")
    client.post(
        "/api/content-bank",
        json={
            "category": "insights",
            "raw_text": "A founder told me content feels hard because useful context is scattered across notes, calls, and decisions.",
        },
    )

    response = client.post(
        "/api/chat/message",
        json={"message": "Draft a post from my latest memory"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_created" in payload["actions"]
    assert "scattered across notes" in payload["post"]["content"]
    assert payload["post"]["title"] != "Draft a post from my latest memory"

    client.post("/api/reset")


def test_draft_includes_variants_and_can_apply_one():
    client.post("/api/reset")
    client.post(
        "/api/content-bank",
        json={
            "category": "insights",
            "raw_text": "A founder told me content gets stuck because the useful context is scattered across calls and notes.",
        },
    )
    draft = client.post(
        "/api/drafts",
        json={"topic": "turning scattered founder context into content"},
    ).json()

    assert len(draft["variants"]) == 3
    assert {variant["id"] for variant in draft["variants"]} == {
        "personal_story",
        "industry_pov",
        "practical_lesson",
    }

    response = client.post(
        f"/api/drafts/{draft['id']}/use-variant",
        json={"variant_id": "practical_lesson"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["selected_variant_id"] == "practical_lesson"
    assert updated["version"] == 2
    assert "1/ Capture the real moment" in updated["content"]

    client.post("/api/reset")


def test_quick_cta_edit_has_fallback_behavior():
    client.post("/api/reset")
    draft = client.post(
        "/api/drafts",
        json={"topic": "why founder content needs workflow ownership"},
    ).json()

    response = client.post(
        f"/api/drafts/{draft['id']}/edit",
        json={"instructions": "Add a clearer CTA"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["version"] == 2
    assert "What part of this workflow" in updated["content"]

    client.post("/api/reset")


def test_profile_voice_controls_are_saved_and_affect_fallback_cta():
    client.post("/api/reset")
    profile_response = client.put(
        "/api/profile",
        json={
            "writing_style": "Reflective, concise, and specific.",
            "writing_samples": ["A sample post with a direct founder lesson."],
            "preferred_structure": "Hook, real moment, lesson, question",
            "avoided_phrases": ["game changer", "unlock"],
            "cta_style": "Invite comments",
        },
    )

    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["writing_samples"] == ["A sample post with a direct founder lesson."]
    assert profile["avoided_phrases"] == ["game changer", "unlock"]

    draft = client.post(
        "/api/drafts",
        json={"topic": "why founder content needs workflow ownership"},
    ).json()
    assert "What would you add from your own experience?" in draft["content"]

    client.post("/api/reset")
