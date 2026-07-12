import hashlib
import logging
from dataclasses import dataclass
from html import escape
from threading import Lock
from urllib.parse import urlencode

import httpx

from app.core.config import is_production_environment, settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str
    action_url: str | None = None


@dataclass(frozen=True)
class EmailSendResult:
    delivered: bool
    delivery_configured: bool
    debug_url: str | None = None


email_outbox: list[EmailMessage] = []
_outbox_lock = Lock()


class EmailService:
    @property
    def provider(self) -> str:
        return settings.EMAIL_PROVIDER.strip().lower()

    @property
    def delivery_configured(self) -> bool:
        if self.provider == "console":
            return not is_production_environment()
        if self.provider == "resend":
            return bool(settings.RESEND_API_KEY and settings.EMAIL_FROM.strip())
        return False

    @staticmethod
    def _action_url(parameter: str, token: str) -> str:
        base_url = settings.APP_BASE_URL.rstrip("/")
        return f"{base_url}/#{urlencode({parameter: token})}"

    def verification_url(self, token: str) -> str:
        return self._action_url("verify_email", token)

    def password_reset_url(self, token: str) -> str:
        return self._action_url("reset_password", token)

    def debug_verification_url(self, token: str | None) -> str | None:
        if not token or self.provider != "console" or is_production_environment():
            return None
        return self.verification_url(token)

    def debug_password_reset_url(self, token: str | None) -> str | None:
        if not token or self.provider != "console" or is_production_environment():
            return None
        return self.password_reset_url(token)

    def send_verification(self, user: dict, token: str) -> EmailSendResult:
        action_url = self.verification_url(token)
        name = user.get("user_name") or "there"
        return self._send(
            EmailMessage(
                to=user["email"],
                subject="Verify your Blidx email",
                text=(
                    f"Hi {name},\n\nVerify your Blidx email by opening this link:\n"
                    f"{action_url}\n\nThis link expires in 24 hours."
                ),
                html=self._action_email_html(
                    name=name,
                    heading="Verify your email",
                    body="Confirm this email address to finish securing your Blidx account.",
                    button_label="Verify email",
                    action_url=action_url,
                    expiry="This link expires in 24 hours.",
                ),
                action_url=action_url,
            ),
            kind="verify-email",
        )

    def send_password_reset(self, user: dict, token: str) -> EmailSendResult:
        action_url = self.password_reset_url(token)
        name = user.get("user_name") or "there"
        return self._send(
            EmailMessage(
                to=user["email"],
                subject="Reset your Blidx password",
                text=(
                    f"Hi {name},\n\nReset your Blidx password by opening this link:\n"
                    f"{action_url}\n\nThis link expires in 30 minutes. If you did not "
                    "request it, you can ignore this email."
                ),
                html=self._action_email_html(
                    name=name,
                    heading="Reset your password",
                    body="Use the secure link below to choose a new Blidx password.",
                    button_label="Reset password",
                    action_url=action_url,
                    expiry=(
                        "This link expires in 30 minutes. If you did not request "
                        "it, you can ignore this email."
                    ),
                ),
                action_url=action_url,
            ),
            kind="reset-password",
        )

    def send_password_changed(self, user: dict) -> EmailSendResult:
        name = user.get("user_name") or "there"
        return self._send(
            EmailMessage(
                to=user["email"],
                subject="Your Blidx password was changed",
                text=(
                    f"Hi {name},\n\nYour Blidx password was changed and existing "
                    "sessions were signed out. If this was not you, contact the "
                    "Blidx team immediately."
                ),
                html=(
                    f"<p>Hi {escape(str(name))},</p>"
                    "<p>Your Blidx password was changed and existing sessions were "
                    "signed out.</p><p>If this was not you, contact the Blidx team "
                    "immediately.</p>"
                ),
            ),
            kind=(
                "password-changed-"
                f"{user.get('password_changed_at') or user.get('session_version', 'unknown')}"
            ),
        )

    def _send(self, message: EmailMessage, kind: str) -> EmailSendResult:
        if not self.delivery_configured:
            return EmailSendResult(delivered=False, delivery_configured=False)

        if self.provider == "console":
            with _outbox_lock:
                email_outbox.append(message)
            return EmailSendResult(
                delivered=True,
                delivery_configured=True,
                debug_url=message.action_url,
            )

        idempotency_source = f"{kind}:{message.to}:{message.action_url or message.text}"
        idempotency_key = hashlib.sha256(
            idempotency_source.encode("utf-8")
        ).hexdigest()
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.text,
                    "html": message.html,
                },
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Account email delivery failed for %s: %s",
                kind,
                type(exc).__name__,
            )
            return EmailSendResult(delivered=False, delivery_configured=True)
        return EmailSendResult(delivered=True, delivery_configured=True)

    @staticmethod
    def _action_email_html(
        *,
        name: str,
        heading: str,
        body: str,
        button_label: str,
        action_url: str,
        expiry: str,
    ) -> str:
        return (
            f"<p>Hi {escape(str(name))},</p>"
            f"<h2>{escape(heading)}</h2>"
            f"<p>{escape(body)}</p>"
            f'<p><a href="{escape(action_url, quote=True)}" style="display:inline-block;'
            "padding:12px 18px;background:#5548b8;color:#fff;text-decoration:none;"
            f'border-radius:10px">{escape(button_label)}</a></p>'
            f"<p>{escape(expiry)}</p>"
        )


email_service = EmailService()
