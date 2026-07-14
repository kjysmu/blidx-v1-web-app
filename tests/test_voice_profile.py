from fastapi.testclient import TestClient

from app.demo_store import DemoStore
from app.main import app
from app.services.draft_quality_service import DraftQualityService
from app.services.voice_profile_service import VoiceProfileService


client = TestClient(app)


VOICE_SAMPLES = [
    (
        "I changed my mind about founder content this week. The useful part was not a better hook. "
        "It was noticing the decision I nearly skipped. I wrote that down before it became a tidy lesson. "
        "That smaller note felt more honest than the polished version. What are you noticing in your own work?"
    ),
    (
        "I used to wait until an idea felt complete. Now I save the rough edge first. The unfinished part "
        "usually contains the point of view. My drafts are shorter because I no longer explain every step. "
        "I leave room for the reader to make the final connection. Does your best writing start finished?"
    ),
    (
        "We reviewed three posts that sounded correct and forgot all of them. Then we read one field note "
        "with an awkward sentence and a real decision. That was the one people remembered. I do not think "
        "human voice means adding more personality words. It means keeping the detail that cost something."
    ),
]


def test_voice_profile_calibrates_from_three_real_samples():
    profile = VoiceProfileService.analyze(VOICE_SAMPLES)

    assert profile["readiness"] == "calibrated"
    assert profile["sample_count"] == 3
    assert profile["total_words"] >= 150
    assert profile["first_person_rate"] > 0
    assert profile["preferred_opening"] in {"first_person", "statement"}
    assert "Calibrated from 3 samples" in profile["summary"]


def test_profile_update_persists_derived_voice_fingerprint():
    client.post("/api/reset")
    response = client.put("/api/profile", json={"writing_samples": VOICE_SAMPLES})

    assert response.status_code == 200
    assert response.json()["voice_profile"]["readiness"] == "calibrated"
    assert client.get("/api/state").json()["profile"]["voice_profile"]["sample_count"] == 3
    client.post("/api/reset")


def test_voice_match_uses_calibrated_rhythm_instead_of_raw_keyword_overlap():
    profile = {
        "writing_samples": VOICE_SAMPLES,
        "voice_profile": VoiceProfileService.analyze(VOICE_SAMPLES),
    }
    matching = (
        "I noticed a small product decision today. It changed how I think about the work. "
        "The useful lesson is still unfinished. What would you keep from this moment?"
    )
    mismatched = (
        "Organizations seeking to maximize strategic outcomes should comprehensively operationalize "
        "cross-functional methodologies while systematically evaluating the broader implications of "
        "technology adoption across a diverse and continuously evolving stakeholder landscape."
    )

    matching_score, _ = VoiceProfileService.match(profile, matching)
    mismatched_score, _ = VoiceProfileService.match(profile, mismatched)

    assert matching_score > mismatched_score


def test_quality_review_resolves_selected_content_bank_text_for_claims():
    state = {
        "profile": {"writing_samples": [], "voice_profile": VoiceProfileService.analyze([])},
        "posts": [],
        "content_bank": [
            {
                "id": "source-1",
                "raw_text": "The pilot found that 73% of composers used AI for exploration, not replacement.",
            }
        ],
    }
    post = {
        "id": "post-1",
        "topic": "AI can help human composers",
        "content": "AI can help human composers explore ideas. In the pilot, 73% used it for exploration.",
        "source_ids": ["source-1"],
        "sources": [{"memory_id": "source-1", "type": "content_bank"}],
    }

    review = DraftQualityService.evaluate(state, post, DemoStore._robotic_phrases())
    factual = next(item for item in review["dimensions"] if item["id"] == "factual_safety")
    specificity = next(item for item in review["dimensions"] if item["id"] == "specificity")

    assert factual["score"] == 5
    assert specificity["score"] >= 4
    assert review["quality_gate"]["status"] != "blocked"


def test_structured_feedback_becomes_a_future_drafting_rule():
    client.post("/api/reset")
    draft = client.post("/api/drafts", json={"topic": "a practical founder content workflow"}).json()
    response = client.post(
        f"/api/drafts/{draft['id']}/feedback",
        json={
            "sentiment": "needs_work",
            "reason": "The point is buried.",
            "tags": ["too_generic", "wrong_emphasis"],
        },
    )

    assert response.status_code == 200
    assert response.json()["metadata"]["tags"] == ["too_generic", "wrong_emphasis"]
    context = DraftQualityService.feedback_context(client.get("/api/state").json())
    assert "Ground the next draft" in context
    assert "requested topic" in context
    client.post("/api/reset")
