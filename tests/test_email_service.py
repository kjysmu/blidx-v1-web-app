import httpx

from app.core.config import settings
from app.services.email_service import EmailService, email_outbox


USER = {
    "email": "email-test@example.com",
    "user_name": "Email Tester",
}


def test_console_email_exposes_action_link_only_in_local_mode(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(settings, "ENVIRONMENT", "local")
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://testserver")
    email_outbox.clear()
    service = EmailService()

    result = service.send_verification(USER, "verification-token-value")

    assert result.delivered is True
    assert result.debug_url == (
        "http://testserver/#verify_email=verification-token-value"
    )
    assert len(email_outbox) == 1
    assert email_outbox[0].to == USER["email"]
    assert "verification-token-value" in email_outbox[0].action_url

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert service.debug_verification_url("secret-token") is None
    assert service.delivery_configured is False


def test_resend_adapter_sends_authenticated_idempotent_request(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "resend-test-key")
    monkeypatch.setattr(settings, "EMAIL_FROM", "Blidx <security@blidx.test>")
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://app.blidx.test")
    captured = {}

    class SuccessfulResponse:
        @staticmethod
        def raise_for_status():
            return None

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SuccessfulResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    result = EmailService().send_password_reset(USER, "reset-token-value")

    assert result.delivered is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer resend-test-key"
    assert len(captured["headers"]["Idempotency-Key"]) == 64
    assert captured["json"]["from"] == "Blidx <security@blidx.test>"
    assert captured["json"]["to"] == [USER["email"]]
    assert "#reset_password=reset-token-value" in captured["json"]["text"]


def test_resend_failure_does_not_raise_into_account_flow(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "resend-test-key")
    monkeypatch.setattr(settings, "EMAIL_FROM", "Blidx <security@blidx.test>")

    def failed_post(*args, **kwargs):
        raise httpx.ConnectError("network unavailable")

    monkeypatch.setattr(httpx, "post", failed_post)

    result = EmailService().send_password_changed(USER)

    assert result.delivered is False
    assert result.delivery_configured is True
