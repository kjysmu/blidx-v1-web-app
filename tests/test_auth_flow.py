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
