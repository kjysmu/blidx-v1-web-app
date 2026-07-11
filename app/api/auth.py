from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

from app.auth_store import auth_store
from app.core.security import create_access_token, decode_access_token
from app.core.security import decode_linkedin_oauth_state
from app.demo_store import current_user_id, demo_store
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse
from app.integrations.linkedin import LinkedInClient

router = APIRouter()


def linkedin_error_status(error: str) -> str:
    if error in {"user_cancelled_login", "user_cancelled_authorize", "access_denied"}:
        return "cancelled"
    if error in {"invalid_scope", "invalid_scope_error", "unauthorized_scope_error"}:
        return "invalid_scope"
    if error in {"invalid_redirect_uri", "redirect_uri_mismatch"}:
        return "invalid_redirect"
    return "failed"


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest):
    try:
        user = auth_store.register(
            payload.email,
            payload.password,
            payload.user_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    demo_store.ensure_user_state(user)
    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user["email"],
        "user_name": user.get("user_name"),
    }


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = auth_store.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    demo_store.ensure_user_state(user)
    return {
        "access_token": create_access_token(user["id"]),
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user["email"],
        "user_name": user.get("user_name"),
    }


@router.get("/me")
def me(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    user = auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/linkedin/callback")
def linkedin_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if not state:
        return RedirectResponse(url="/?linkedin=invalid_callback", status_code=303)

    oauth_state = decode_linkedin_oauth_state(state)
    if not oauth_state:
        return RedirectResponse(url="/?linkedin=invalid_state", status_code=303)
    user = auth_store.get_user(oauth_state["user_id"])
    if not user:
        return RedirectResponse(url="/?linkedin=unknown_user", status_code=303)

    demo_store.ensure_user_state(user)
    previous_user = current_user_id.set(user["id"])
    try:
        if not demo_store.consume_linkedin_oauth(oauth_state["nonce"]):
            return RedirectResponse(url="/?linkedin=expired_state", status_code=303)

        if error:
            status = linkedin_error_status(error)
            return RedirectResponse(url=f"/?linkedin={status}", status_code=303)
        if not code:
            return RedirectResponse(url="/?linkedin=invalid_callback", status_code=303)

        linkedin = LinkedInClient()
        token = linkedin.exchange_code_for_token(code)
        access_token = token.get("access_token")
        if not access_token:
            return RedirectResponse(url="/?linkedin=token_error", status_code=303)
        profile = linkedin.get_userinfo(access_token)
        demo_store.store_linkedin_connection(token, profile)
        return RedirectResponse(url="/?linkedin=connected", status_code=303)
    except Exception:
        return RedirectResponse(url="/?linkedin=failed", status_code=303)
    finally:
        current_user_id.reset(previous_user)
