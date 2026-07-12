from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from jose import jwt
from passlib.hash import pbkdf2_sha256

from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    PASSWORD_HASH_ROUNDS,
    create_linkedin_oauth_state,
    hash_password,
    verify_and_update_password,
)
from app.main import app


client = TestClient(app)
ORIGINAL_PASSWORD = "strong-password-123"
NEW_PASSWORD = "new-strong-password-456"


def unique_email(prefix: str = "security") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def register_user(email: str | None = None) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": email or unique_email(),
            "password": ORIGINAL_PASSWORD,
            "user_name": "Security Tester",
        },
    )
    assert response.status_code == 200
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(email: str, password: str) -> dict:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def assert_revoked(token: str) -> None:
    response = client.get("/auth/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_revoked"


def test_password_hashes_use_current_rounds_and_legacy_hashes_upgrade():
    current_hash = hash_password(ORIGINAL_PASSWORD)
    assert pbkdf2_sha256.from_string(current_hash).rounds == PASSWORD_HASH_ROUNDS

    legacy_hash = pbkdf2_sha256.using(rounds=29_000).hash(ORIGINAL_PASSWORD)
    verified, replacement = verify_and_update_password(ORIGINAL_PASSWORD, legacy_hash)

    assert verified is True
    assert replacement is not None
    assert pbkdf2_sha256.from_string(replacement).rounds == PASSWORD_HASH_ROUNDS


def test_change_password_revokes_old_sessions_and_keeps_current_device_signed_in():
    account = register_user()
    second_session = login(account["email"], ORIGINAL_PASSWORD)

    wrong_password = client.post(
        "/auth/change-password",
        headers=bearer(account["access_token"]),
        json={
            "current_password": "not-the-current-password",
            "new_password": NEW_PASSWORD,
        },
    )
    assert wrong_password.status_code == 400
    assert wrong_password.json()["detail"]["code"] == "password_change_failed"

    changed = client.post(
        "/auth/change-password",
        headers=bearer(account["access_token"]),
        json={
            "current_password": ORIGINAL_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200
    fresh_session = changed.json()

    assert_revoked(account["access_token"])
    assert_revoked(second_session["access_token"])
    assert client.get(
        "/auth/me", headers=bearer(fresh_session["access_token"])
    ).status_code == 200

    old_login = client.post(
        "/auth/login",
        json={"email": account["email"], "password": ORIGINAL_PASSWORD},
    )
    assert old_login.status_code == 401
    assert old_login.json()["detail"]["code"] == "invalid_credentials"
    assert login(account["email"], NEW_PASSWORD)["access_token"]


def test_logout_all_devices_revokes_every_current_token():
    account = register_user()
    second_session = login(account["email"], ORIGINAL_PASSWORD)

    wrong_password = client.post(
        "/auth/logout-all",
        headers=bearer(account["access_token"]),
        json={"current_password": "wrong-password"},
    )
    assert wrong_password.status_code == 400
    assert client.get(
        "/auth/me", headers=bearer(second_session["access_token"])
    ).status_code == 200

    revoked = client.post(
        "/auth/logout-all",
        headers=bearer(account["access_token"]),
        json={"current_password": ORIGINAL_PASSWORD},
    )
    assert revoked.status_code == 200

    assert_revoked(account["access_token"])
    assert_revoked(second_session["access_token"])
    assert login(account["email"], ORIGINAL_PASSWORD)["access_token"]


def test_expired_and_wrong_purpose_tokens_return_specific_session_errors():
    account = register_user()
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode(
        {
            "sub": account["user_id"],
            "ver": 1,
            "purpose": "access",
            "iat": now - timedelta(days=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    expired = client.get("/auth/me", headers=bearer(expired_token))
    assert expired.status_code == 401
    assert expired.json()["detail"] == {
        "code": "session_expired",
        "message": "Your session expired. Please sign in again.",
    }

    oauth_state = create_linkedin_oauth_state(account["user_id"], "test-nonce")
    wrong_purpose = client.get("/auth/me", headers=bearer(oauth_state))
    assert wrong_purpose.status_code == 401
    assert wrong_purpose.json()["detail"]["code"] == "invalid_session"


def test_legacy_access_token_without_version_remains_compatible():
    account = register_user()
    token = jwt.encode(
        {
            "sub": account["user_id"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get("/auth/me", headers=bearer(token))
    assert response.status_code == 200
    assert response.json()["email"] == account["email"]


def test_login_rate_limit_returns_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
    login_rate_limiter.clear()
    headers = {"x-forwarded-for": f"192.0.2.{uuid.uuid4().int % 200 + 1}"}
    payload = {"email": unique_email("unknown"), "password": "bad-password"}

    try:
        statuses = [
            client.post("/auth/login", headers=headers, json=payload).status_code
            for _ in range(3)
        ]
        blocked = client.post("/auth/login", headers=headers, json=payload)
    finally:
        login_rate_limiter.clear()

    assert statuses == [401, 401, 429]
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "login_rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


def test_account_lockout_is_enforced_independently_of_request_throttle(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MAX_FAILED_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_ATTEMPTS", 100)
    login_rate_limiter.clear()
    account = register_user()
    headers = {"x-forwarded-for": f"198.51.100.{uuid.uuid4().int % 200 + 1}"}
    payload = {"email": account["email"], "password": "bad-password"}

    try:
        first = client.post("/auth/login", headers=headers, json=payload)
        second = client.post("/auth/login", headers=headers, json=payload)
        correct_while_locked = client.post(
            "/auth/login",
            headers=headers,
            json={"email": account["email"], "password": ORIGINAL_PASSWORD},
        )
    finally:
        login_rate_limiter.clear()

    assert first.status_code == 401
    assert second.status_code == 429
    assert correct_while_locked.status_code == 429
    assert second.json()["detail"]["code"] == "login_rate_limited"
    assert "Retry-After" in second.headers
