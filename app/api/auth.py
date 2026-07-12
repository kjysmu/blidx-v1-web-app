from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth_store import auth_store
from app.api.deps import require_request_user
from app.core.rate_limit import login_rate_limiter
from app.core.security import create_access_token, decode_linkedin_oauth_state
from app.demo_store import current_user_id, demo_store
from app.integrations.linkedin import LinkedInClient
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    RevokeSessionsRequest,
)

router = APIRouter()


def auth_response(user: dict) -> dict:
    return {
        "access_token": create_access_token(
            user["id"], int(user.get("session_version", 1))
        ),
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user["email"],
        "user_name": user.get("user_name"),
    }


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "login_rate_limited",
            "message": "Too many sign-in attempts. Please wait and try again.",
        },
        headers={"Retry-After": str(max(1, retry_after))},
    )


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
    return auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request):
    email = str(payload.email).strip().lower()
    ip_address = client_ip(request)
    retry_after = login_rate_limiter.retry_after(ip_address, email)
    if retry_after:
        raise rate_limited(retry_after)

    result = auth_store.authenticate(email, payload.password)
    if result.status == "locked":
        login_rate_limiter.record_failure(ip_address, email)
        raise rate_limited(result.retry_after_seconds or 1)
    if result.status != "ok" or not result.user:
        login_rate_limiter.record_failure(ip_address, email)
        retry_after = login_rate_limiter.retry_after(ip_address, email)
        if retry_after:
            raise rate_limited(retry_after)
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_credentials",
                "message": "Invalid email or password.",
            },
        )

    login_rate_limiter.record_success(email)
    demo_store.ensure_user_state(result.user)
    return auth_response(result.user)


@router.get("/me")
def me(user: dict = Depends(require_request_user)) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "user_name": user.get("user_name"),
        "created_at": user.get("created_at"),
        "password_changed_at": user.get("password_changed_at"),
        "last_login_at": user.get("last_login_at"),
    }


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    payload: ChangePasswordRequest,
    user: dict = Depends(require_request_user),
) -> dict:
    try:
        updated_user = auth_store.change_password(
            user["id"], payload.current_password, payload.new_password
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "password_change_failed", "message": str(exc)},
        ) from exc
    return auth_response(updated_user)


@router.post("/logout-all")
def logout_all_devices(
    payload: RevokeSessionsRequest,
    user: dict = Depends(require_request_user),
) -> dict:
    try:
        auth_store.revoke_all_sessions(user["id"], payload.current_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "session_revocation_failed", "message": str(exc)},
        ) from exc
    return {"message": "All sessions have been signed out."}


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
