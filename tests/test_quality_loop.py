from fastapi.testclient import TestClient

from app.demo_store import DemoStore
from app.main import app
from app.quality_benchmarks import BENCHMARK_SCENARIOS
from app.services.draft_quality_service import DraftQualityService


client = TestClient(app)


def test_draft_quality_has_six_measurable_dimensions():
    client.post("/api/reset")
    client.put(
        "/api/profile",
        json={
            "writing_samples": [
                "I tested this with three founders.\n\nThe useful lesson was smaller than I expected.\n\nWhat are you seeing?"
            ]
        },
    )
    client.post(
        "/api/content-bank",
        json={"raw_text": "This week I tested a Postgres migration with three founder accounts."},
    )

    draft = client.post(
        "/api/drafts",
        json={"topic": "what a Postgres migration taught me about founder software"},
    ).json()
    review = draft["quality_review"]

    assert draft["topic"] == "what a Postgres migration taught me about founder software"
    assert review["dimension_max"] == 30
    assert 0 <= review["readiness_percent"] <= 100
    assert {item["id"] for item in review["dimensions"]} == {
        "topic_fidelity",
        "voice_fidelity",
        "specificity",
        "factual_safety",
        "structure_variety",
        "publish_readiness",
    }
    client.post("/api/reset")


def test_quality_service_flags_unsupported_numeric_claims():
    state = {"profile": {"writing_samples": []}, "posts": []}
    post = {
        "id": "post-1",
        "topic": "AI in healthcare",
        "title": "AI in healthcare",
        "content": "AI reduced waiting time by 73% across 400 clinics.\n\nThat changes healthcare.",
        "sources": [{"raw_text": "A clinician said AI may help with administrative work."}],
    }

    review = DraftQualityService.evaluate(state, post, DemoStore._robotic_phrases())
    factual = next(item for item in review["dimensions"] if item["id"] == "factual_safety")

    assert factual["score"] == 1
    assert "73%" in factual["detail"]


def test_quality_service_does_not_treat_numbered_lists_as_factual_claims():
    state = {"profile": {"writing_samples": []}, "posts": []}
    post = {
        "id": "post-1",
        "topic": "founder content workflow",
        "title": "Founder content workflow",
        "content": "1/ Capture the moment.\n\n2/ Find the tension.\n\n3/ Write the point of view.",
        "sources": [],
    }

    review = DraftQualityService.evaluate(state, post, DemoStore._robotic_phrases())
    factual = next(item for item in review["dimensions"] if item["id"] == "factual_safety")

    assert factual["score"] == 5


def test_feedback_actions_build_a_workspace_quality_report():
    client.post("/api/reset")
    draft = client.post(
        "/api/drafts",
        json={"topic": "why founder content needs a real operating workflow"},
    ).json()

    rating = client.post(
        f"/api/drafts/{draft['id']}/feedback",
        json={"sentiment": "needs_work", "reason": "The hook is too formal"},
    )
    assert rating.status_code == 200
    assert rating.json()["event"] == "voice_rating"

    client.post(
        f"/api/drafts/{draft['id']}/edit",
        json={"instructions": "Make the hook shorter and more personal"},
    )
    client.post(
        f"/api/drafts/{draft['id']}/approve",
        json={"schedule_type": "best_time"},
    )

    report = client.get("/api/quality/report").json()
    state = client.get("/api/state").json()
    assert report["drafts_evaluated"] == 1
    assert report["voice_ratings"] == 1
    assert report["voice_match_percent"] == 0
    assert report["revision_count"] == 1
    assert report["approval_count"] == 1
    assert any(item["request"] == "shorter" for item in report["common_revision_requests"])
    assert len(state["draft_feedback"]) == 3
    assert "Revision requested" in DraftQualityService.feedback_context(state)
    client.post("/api/reset")


def test_quality_benchmark_catalog_covers_five_content_risks():
    response = client.get("/api/quality/benchmarks")
    assert response.status_code == 200
    assert response.json()["count"] == 5
    assert response.json()["scenarios"] == BENCHMARK_SCENARIOS
    assert {item["category"] for item in BENCHMARK_SCENARIOS} == {
        "personal_story",
        "industry_opinion",
        "event",
        "technical_lesson",
        "healthcare",
    }
