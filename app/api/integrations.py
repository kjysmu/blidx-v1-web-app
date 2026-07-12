import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_request_user, use_request_user
from app.core.config import settings
from app.core.security import create_linkedin_oauth_state
from app.demo_store import demo_store
from app.demo_store import utc_now
from app.integrations.linkedin import LinkedInClient, linkedin_share_url
from app.services.email_service import email_service

router = APIRouter(dependencies=[Depends(use_request_user)])


class LinkedInConnectResponse(BaseModel):
    configured: bool
    authorization_url: str | None = None
    fallback_url: str
    message: str


@router.get("/status")
def integration_status() -> dict:
    linkedin = LinkedInClient()
    state = demo_store.snapshot()
    linkedin_state = state.get("linkedin") or {}
    return {
        "anthropic": {
            "configured": bool(settings.ANTHROPIC_API_KEY),
            "model": settings.ANTHROPIC_MODEL,
        },
        "database": {
            "storage": "postgres" if settings.USE_DATABASE_STORAGE else "file",
            "configured": bool(settings.DATABASE_URL),
            "persistent_auth": bool(settings.USE_DATABASE_STORAGE and settings.DATABASE_URL),
            "workspace_schema": "relational-v1" if settings.USE_DATABASE_STORAGE else "json-files",
        },
        "account_email": {
            "configured": email_service.delivery_configured,
            "provider": email_service.provider,
            "verification_required": settings.EMAIL_VERIFICATION_REQUIRED,
        },
        "linkedin": {
            "configured": linkedin.configured,
            "connected": bool(linkedin_state.get("connected")),
            "profile": linkedin_state.get("profile"),
            "connected_at": linkedin_state.get("connected_at"),
            "expires_at": linkedin_state.get("expires_at"),
            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            "scopes": settings.LINKEDIN_SCOPES,
            "fallback_url": linkedin_share_url(),
        },
        "payloadcms": {
            "recommendation": "defer",
            "reason": (
                "PayloadCMS is a strong Next.js-native admin/CMS option, but Blidx V1 "
                "already has a FastAPI backend and SQLAlchemy models. A lightweight "
                "/admin view is faster for MVP monitoring; revisit Payload when the "
                "frontend moves to a full Next.js app or marketing-managed content is needed."
            ),
        },
    }


@router.post("/linkedin/connect", response_model=LinkedInConnectResponse)
def linkedin_connect(user: dict = Depends(require_request_user)) -> LinkedInConnectResponse:
    linkedin = LinkedInClient()
    fallback_url = linkedin_share_url()
    if not linkedin.configured:
        return LinkedInConnectResponse(
            configured=False,
            fallback_url=fallback_url,
            message="LinkedIn OAuth is not configured yet. Use copy-and-open fallback.",
        )

    try:
        nonce = secrets.token_urlsafe(32)
        expires_at = utc_now() + timedelta(
            minutes=settings.LINKEDIN_OAUTH_STATE_EXPIRE_MINUTES
        )
        demo_store.begin_linkedin_oauth(nonce, expires_at)
        state = create_linkedin_oauth_state(user["id"], nonce)
        return LinkedInConnectResponse(
            configured=True,
            authorization_url=linkedin.get_oauth_url(state),
            fallback_url=fallback_url,
            message="LinkedIn OAuth is ready for this Blidx account.",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/linkedin/disconnect")
def linkedin_disconnect(_: dict = Depends(require_request_user)) -> dict:
    return demo_store.disconnect_linkedin()
