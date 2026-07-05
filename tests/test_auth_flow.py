import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def unique_email(prefix: str = "tester") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def register_user(email: str | None = None, name: str = "Tester") -> dict:
    payload = {
        "email": email or unique_email(),
        "password": "strong-password-123",
        "user_name": name,
    }
    response = client.post("/auth/register", json=payload)
    if response.status_code == 409 and email is None:
        payload["email"] = unique_email()
        response = client.post("/auth/register", json=payload)
    assert response.status_code == 200
    return response.json()


def test_register_login_and_me():
    email = unique_email()
    auth = register_user(email=email, name="Jae Test")

    assert auth["access_token"]
    assert auth["token_type"] == "bearer"
    assert auth["email"] == email
    assert auth["user_name"] == "Jae Test"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email

    login = client.post(
        "/auth/login",
        json={"email": email, "password": "strong-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["user_id"] == auth["user_id"]


def test_authenticated_workspaces_are_isolated():
    first = register_user(name="First User")
    second = register_user(name="Second User")
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}

    first_memory = client.post(
        "/api/content-bank",
        json={"raw_text": "First user launched a private onboarding flow."},
        headers=first_headers,
    )
    assert first_memory.status_code == 200

    first_state = client.get("/api/state", headers=first_headers).json()
    second_state = client.get("/api/state", headers=second_headers).json()

    assert first_state["auth"]["authenticated"] is True
    assert second_state["auth"]["authenticated"] is True
    assert first_state["user"]["user_name"] == "First User"
    assert second_state["user"]["user_name"] == "Second User"
    assert len(first_state["content_bank"]) == 1
    assert second_state["content_bank"] == []


def test_authenticated_user_can_complete_onboarding():
    auth = register_user(name="Onboard User")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    initial_state = client.get("/api/state", headers=headers).json()
    assert initial_state["onboarding_completed"] is False

    response = client.post(
        "/api/onboarding/complete",
        headers=headers,
        json={
            "first_name": "Mina",
            "role": "Founder",
            "company_name": "CareLoop",
            "company_website": "https://careloop.example",
            "industry": "Digital health",
            "company_description": "CareLoop helps clinics keep patients connected between sessions.",
            "audience": ["Founders", "Clinicians"],
            "expertise": ["Mental health", "Care operations"],
            "content_types": ["Industry insights", "Personal stories"],
            "posting_frequency": "3-4x_per_week",
            "tone": "Warm & personal",
            "writing_style": "Reflective and practical.",
            "first_memory": "I spoke with a clinician who said follow-up care is where patients often feel alone.",
        },
    )

    assert response.status_code == 200
    state = response.json()
    assert state["onboarding_completed"] is True
    assert state["profile"]["company_name"] == "CareLoop"
    assert state["profile"]["audience"] == ["Founders", "Clinicians"]
    assert len(state["content_bank"]) == 1
    assert "clinician" in state["content_bank"][0]["raw_text"]


def test_authenticated_chat_draft_keeps_session():
    auth = register_user(name="Chat User")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    response = client.post(
        "/api/chat/message",
        headers=headers,
        json={"message": "write a draft about ai and healthcare"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"] == ["context_requested"]
    assert payload["post"] is None
    assert payload["state"]["auth"]["authenticated"] is True
    assert payload["state"]["auth"]["user_id"] == auth["user_id"]

    response = client.post(
        "/api/chat/message",
        headers=headers,
        json={"message": "just draft it"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_created" in payload["actions"]
    assert payload["state"]["auth"]["authenticated"] is True
    assert payload["state"]["auth"]["user_id"] == auth["user_id"]
