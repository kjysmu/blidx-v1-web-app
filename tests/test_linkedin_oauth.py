import json
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import decode_linkedin_oauth_state
from app.core.token_crypto import decrypt_token, encrypt_token
from app.demo_store import current_user_id, demo_store
from app.integrations.linkedin import LinkedInClient
from app.main import app


client = TestClient(app)


def register(name: str) -> tuple[dict, dict]:
    response = client.post(
        "/auth/register",
        json={
            "email": f"linkedin-{uuid.uuid4().hex}@example.com",
            "password": "strong-password-123",
            "user_name": name,
        },
    )
    assert response.status_code == 200
    auth = response.json()
    return auth, {"Authorization": f"Bearer {auth['access_token']}"}


def configure_linkedin(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(
        settings,
        "LINKEDIN_REDIRECT_URI",
        "https://app.blidx.test/auth/linkedin/callback",
    )
    monkeypatch.setattr(settings, "LINKEDIN_TOKEN_ENCRYPTION_KEY", "test-encryption-key")


def test_linkedin_connect_requires_a_signed_in_blidx_user(monkeypatch):
    configure_linkedin(monkeypatch)
    response = client.post("/api/integrations/linkedin/connect")
    assert response.status_code == 401


def test_app_has_one_canonical_linkedin_callback():
    callbacks = [
        route.path
        for route in app.routes
        if getattr(route, "path", None) and route.path.endswith("/linkedin/callback")
    ]
    assert callbacks == ["/auth/linkedin/callback"]


def test_linkedin_oauth_is_one_time_encrypted_and_account_bound(monkeypatch):
    configure_linkedin(monkeypatch)
    first, first_headers = register("First LinkedIn User")
    _, second_headers = register("Second LinkedIn User")

    connect = client.post(
        "/api/integrations/linkedin/connect",
        headers=first_headers,
    )
    assert connect.status_code == 200
    authorization_url = connect.json()["authorization_url"]
    oauth_token = parse_qs(urlparse(authorization_url).query)["state"][0]
    oauth_state = decode_linkedin_oauth_state(oauth_token)
    assert oauth_state["user_id"] == first["user_id"]

    public_before = client.get("/api/state", headers=first_headers).json()
    assert "linkedin_oauth" not in public_before

    monkeypatch.setattr(
        LinkedInClient,
        "exchange_code_for_token",
        lambda self, code: {
            "access_token": "first-user-linkedin-token",
            "refresh_token": "first-user-refresh-token",
            "expires_in": 3600,
        },
    )
    monkeypatch.setattr(
        LinkedInClient,
        "get_userinfo",
        lambda self, token: {"sub": "linkedin-person-1", "name": "First LinkedIn"},
    )

    callback = client.get(
        "/auth/linkedin/callback",
        params={"code": "valid-code", "state": oauth_token},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/?linkedin=connected"

    first_state = client.get("/api/state", headers=first_headers).json()
    second_state = client.get("/api/state", headers=second_headers).json()
    assert first_state["linkedin"]["connected"] is True
    assert first_state["linkedin"]["profile"]["sub"] == "linkedin-person-1"
    assert second_state["linkedin"]["connected"] is False
    assert "access_token" not in str(first_state)
    assert "refresh_token" not in str(first_state)

    previous = current_user_id.set(first["user_id"])
    try:
        raw = demo_store._read()
        linkedin = raw["linkedin"]
        assert linkedin.get("access_token") is None
        assert linkedin["access_token_encrypted"] != "first-user-linkedin-token"
        assert decrypt_token(linkedin["access_token_encrypted"]) == "first-user-linkedin-token"
        assert decrypt_token(linkedin["refresh_token_encrypted"]) == "first-user-refresh-token"
    finally:
        current_user_id.reset(previous)

    replay = client.get(
        "/auth/linkedin/callback",
        params={"code": "replayed-code", "state": oauth_token},
        follow_redirects=False,
    )
    assert replay.status_code == 303
    assert replay.headers["location"] == "/?linkedin=expired_state"

    monkeypatch.setattr(
        LinkedInClient,
        "publish_post",
        lambda self, token, content: {
            "id": "linkedin-post-1",
            "url": "https://www.linkedin.com/feed/update/linkedin-post-1",
        },
    )
    draft = client.post(
        "/api/drafts",
        headers=first_headers,
        json={"topic": "an account-bound LinkedIn publishing test"},
    ).json()
    published = client.post(
        f"/api/drafts/{draft['id']}/publish",
        headers=first_headers,
    )
    assert published.status_code == 200
    assert published.json()["published"] is True
    assert published.json()["mode"] == "oauth"

    disconnected = client.post(
        "/api/integrations/linkedin/disconnect",
        headers=first_headers,
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["connected"] is False


def test_linkedin_callback_rejects_unsigned_state(monkeypatch):
    configure_linkedin(monkeypatch)
    response = client.get(
        "/auth/linkedin/callback",
        params={"code": "code", "state": "not-a-signed-state"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/?linkedin=invalid_state"


def test_expired_linkedin_token_uses_manual_fallback(monkeypatch):
    configure_linkedin(monkeypatch)
    auth, headers = register("Expired LinkedIn User")
    previous = current_user_id.set(auth["user_id"])
    try:
        state = demo_store._read()
        state["linkedin"] = {
            "connected": True,
            "access_token_encrypted": encrypt_token("expired-token"),
            "profile": {"sub": "expired-member"},
            "connected_at": "2020-01-01T00:00:00+00:00",
            "expires_at": "2020-01-01T01:00:00+00:00",
        }
        demo_store._write(state)
    finally:
        current_user_id.reset(previous)

    draft = client.post(
        "/api/drafts",
        headers=headers,
        json={"topic": "an expired LinkedIn token"},
    ).json()
    publish = client.post(f"/api/drafts/{draft['id']}/publish", headers=headers)

    assert publish.status_code == 200
    assert publish.json()["published"] is False
    assert publish.json()["mode"] == "manual_fallback"
    assert client.get("/api/state", headers=headers).json()["linkedin"]["connected"] is False


def test_linkedin_client_uses_versioned_posts_api(monkeypatch):
    configure_linkedin(monkeypatch)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v2/userinfo":
            return httpx.Response(200, json={"sub": "member-123"})
        assert request.url.path == "/rest/posts"
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:123"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    result = LinkedInClient().publish_post("member-token", "A founder post")

    post_request = requests[-1]
    payload = json.loads(post_request.content)
    assert post_request.url.path == "/rest/posts"
    assert post_request.headers["linkedin-version"] == settings.LINKEDIN_API_VERSION
    assert post_request.headers["x-restli-protocol-version"] == "2.0.0"
    assert payload == {
        "author": "urn:li:person:member-123",
        "commentary": "A founder post",
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    assert result["id"] == "urn:li:share:123"
    assert result["url"] == "https://www.linkedin.com/feed/update/urn:li:share:123/"
