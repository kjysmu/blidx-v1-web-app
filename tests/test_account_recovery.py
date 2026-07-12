import uuid
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.auth_store import PASSWORD_RESET_PURPOSE, auth_store
from app.core.config import settings
from app.core.rate_limit import account_email_rate_limiter
from app.main import app
from app.services.email_service import email_outbox


client = TestClient(app)
ORIGINAL_PASSWORD = "recovery-password-123"
NEW_PASSWORD = "recovery-password-456"


def unique_email(prefix: str = "recovery") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def token_from_url(url: str, parameter: str) -> str:
    parsed = urlparse(url)
    return parse_qs(parsed.fragment or parsed.query)[parameter][0]


def configure_console_email(monkeypatch, *, verification_required: bool = False):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://testserver")
    monkeypatch.setattr(
        settings, "EMAIL_VERIFICATION_REQUIRED", verification_required
    )
    email_outbox.clear()
    account_email_rate_limiter.clear()


def register(email: str, password: str = ORIGINAL_PASSWORD) -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, "user_name": "Recovery Tester"},
    )
    assert response.status_code == 200
    return response.json()


def test_required_email_verification_blocks_login_until_single_use_link(monkeypatch):
    configure_console_email(monkeypatch, verification_required=True)
    email = unique_email("verify")

    registration = register(email)
    assert registration["access_token"] is None
    assert registration["verification_required"] is True
    assert registration["delivery_configured"] is True
    assert registration["debug_verification_url"]
    assert len(email_outbox) == 1

    unverified_login = client.post(
        "/auth/login", json={"email": email, "password": ORIGINAL_PASSWORD}
    )
    assert unverified_login.status_code == 403
    assert unverified_login.json()["detail"]["code"] == "email_not_verified"

    token = token_from_url(
        registration["debug_verification_url"], "verify_email"
    )
    stored_data = auth_store.path.read_text()
    assert token not in stored_data
    assert auth_store._token_hash(token) in stored_data

    verified = client.post("/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400

    login = client.post(
        "/auth/login", json={"email": email, "password": ORIGINAL_PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["email_verified"] is True


def test_password_reset_is_generic_single_use_and_revokes_sessions(monkeypatch):
    configure_console_email(monkeypatch)
    email = unique_email("reset")
    registration = register(email)
    original_token = registration["access_token"]
    email_outbox.clear()

    unknown = client.post(
        "/auth/password/forgot", json={"email": unique_email("unknown")}
    )
    known = client.post("/auth/password/forgot", json={"email": email})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]
    assert unknown.json()["delivery_configured"] is True
    assert known.json()["debug_url"]
    assert len(email_outbox) == 1

    repeated = client.post("/auth/password/forgot", json={"email": email})
    assert repeated.status_code == 200
    assert repeated.json()["debug_url"] is None
    assert len(email_outbox) == 1

    reset_token = token_from_url(known.json()["debug_url"], "reset_password")
    same_password = client.post(
        "/auth/password/reset",
        json={"token": reset_token, "new_password": ORIGINAL_PASSWORD},
    )
    assert same_password.status_code == 400
    assert same_password.json()["detail"]["code"] == "password_reset_failed"

    reset = client.post(
        "/auth/password/reset",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert len(email_outbox) == 2
    assert client.post(
        "/auth/password/reset",
        json={"token": reset_token, "new_password": "another-password-789"},
    ).status_code == 400

    revoked = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {original_token}"}
    )
    assert revoked.status_code == 401
    assert revoked.json()["detail"]["code"] == "session_revoked"
    assert client.post(
        "/auth/login", json={"email": email, "password": ORIGINAL_PASSWORD}
    ).status_code == 401
    new_login = client.post(
        "/auth/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200
    assert new_login.json()["email_verified"] is True


def test_expired_password_reset_token_is_rejected(monkeypatch):
    configure_console_email(monkeypatch)
    email = unique_email("expired-reset")
    register(email)
    _, token = auth_store.issue_account_token(email, PASSWORD_RESET_PURPOSE, -1)

    response = client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_reset_token"


def test_manual_password_change_invalidates_outstanding_reset_link(monkeypatch):
    configure_console_email(monkeypatch)
    email = unique_email("manual-change")
    registration = register(email)
    email_outbox.clear()
    forgot = client.post("/auth/password/forgot", json={"email": email})
    reset_token = token_from_url(forgot.json()["debug_url"], "reset_password")

    changed = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {registration['access_token']}"},
        json={
            "current_password": ORIGINAL_PASSWORD,
            "new_password": NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200

    stale_reset = client.post(
        "/auth/password/reset",
        json={"token": reset_token, "new_password": "third-password-789"},
    )
    assert stale_reset.status_code == 400
    assert stale_reset.json()["detail"]["code"] == "invalid_reset_token"


def test_account_email_requests_are_rate_limited_for_unknown_accounts(monkeypatch):
    configure_console_email(monkeypatch)
    monkeypatch.setattr(settings, "ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS", 60)
    headers = {"x-forwarded-for": f"203.0.113.{uuid.uuid4().int % 200 + 1}"}
    payload = {"email": unique_email("rate")}

    try:
        first = client.post("/auth/password/forgot", headers=headers, json=payload)
        second = client.post("/auth/password/forgot", headers=headers, json=payload)
        blocked = client.post("/auth/password/forgot", headers=headers, json=payload)
    finally:
        account_email_rate_limiter.clear()

    assert first.status_code == second.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "account_email_rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


def test_file_tokens_never_store_raw_values(monkeypatch):
    configure_console_email(monkeypatch)
    email = unique_email("storage")
    register(email)
    email_outbox.clear()

    response = client.post("/auth/password/forgot", json={"email": email})
    token = token_from_url(response.json()["debug_url"], "reset_password")
    stored_data = auth_store.path.read_text()

    assert token not in stored_data
    assert auth_store._token_hash(token) in stored_data
