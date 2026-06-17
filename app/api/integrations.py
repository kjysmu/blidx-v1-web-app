import secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.demo_store import demo_store
from app.integrations.linkedin import LinkedInClient, linkedin_share_url

router = APIRouter()


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
        "linkedin": {
            "configured": linkedin.configured,
            "connected": bool(linkedin_state.get("connected")),
            "profile": linkedin_state.get("profile"),
            "connected_at": linkedin_state.get("connected_at"),
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


@router.get("/linkedin/connect", response_model=LinkedInConnectResponse)
def linkedin_connect() -> LinkedInConnectResponse:
    linkedin = LinkedInClient()
    fallback_url = linkedin_share_url()
    if not linkedin.configured:
        return LinkedInConnectResponse(
            configured=False,
            fallback_url=fallback_url,
            message="LinkedIn OAuth is not configured yet. Use copy-and-open fallback.",
        )

    try:
        return LinkedInConnectResponse(
            configured=True,
            authorization_url=linkedin.get_oauth_url(secrets.token_urlsafe(24)),
            fallback_url=fallback_url,
            message="LinkedIn OAuth is ready to start.",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/linkedin/callback")
def linkedin_callback(code: str | None = None, error: str | None = None) -> dict:
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code:
        raise HTTPException(status_code=400, detail="Missing LinkedIn authorization code")

    linkedin = LinkedInClient()
    try:
        token = linkedin.exchange_code_for_token(code)
        profile = linkedin.get_userinfo(token["access_token"])
        demo_store.store_linkedin_connection(token, profile)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="LinkedIn token exchange failed") from exc

    return {
        "connected": True,
        "expires_in": token.get("expires_in"),
        "note": "LinkedIn token exchange succeeded and is stored for this staging demo.",
    }
