from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth_store import (
    EMAIL_VERIFICATION_PURPOSE,
    PASSWORD_RESET_PURPOSE,
    auth_store,
)
from app.api.deps import require_request_user
from app.core.config import settings
from app.core.rate_limit import account_email_rate_limiter, login_rate_limiter
from app.core.security import create_access_token, decode_linkedin_oauth_state
from app.demo_store import current_user_id, demo_store
from app.integrations.linkedin import LinkedInClient
from app.schemas.auth import (
    AccountActionResponse,
    AccountEmailResponse,
    AuthResponse,
    ChangePasswordRequest,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    RegistrationResponse,
    ResetPasswordRequest,
    RevokeSessionsRequest,
    VerifyEmailRequest,
)
from app.services.email_service import email_service

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
        "email_verified": bool(user.get("email_verified_at")),
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


def account_email_rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "account_email_rate_limited",
            "message": "Too many requests. Please wait before trying again.",
        },
        headers={"Retry-After": str(max(1, retry_after))},
    )


def enforce_account_email_limit(request: Request, email: str) -> None:
    ip_address = client_ip(request)
    retry_after = account_email_rate_limiter.retry_after(ip_address, email)
    if retry_after:
        raise account_email_rate_limited(retry_after)
    account_email_rate_limiter.record_failure(ip_address, email)


def linkedin_error_status(error: str) -> str:
    if error in {"user_cancelled_login", "user_cancelled_authorize", "access_denied"}:
        return "cancelled"
    if error in {"invalid_scope", "invalid_scope_error", "unauthorized_scope_error"}:
        return "invalid_scope"
    if error in {"invalid_redirect_uri", "redirect_uri_mismatch"}:
        return "invalid_redirect"
    return "failed"


@router.post("/register", response_model=RegistrationResponse)
def register(payload: RegisterRequest, background_tasks: BackgroundTasks):
    try:
        user = auth_store.register(
            payload.email,
            payload.password,
            payload.user_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    demo_store.ensure_user_state(user)
    token = None
    if email_service.delivery_configured or settings.EMAIL_VERIFICATION_REQUIRED:
        _, token = auth_store.issue_account_token(
            user["email"],
            EMAIL_VERIFICATION_PURPOSE,
            settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES,
        )
        if token and email_service.delivery_configured:
            background_tasks.add_task(email_service.send_verification, user, token)

    response = auth_response(user)
    if settings.EMAIL_VERIFICATION_REQUIRED:
        response["access_token"] = None
        response["token_type"] = None
    response.update(
        {
            "verification_required": settings.EMAIL_VERIFICATION_REQUIRED,
            "delivery_configured": email_service.delivery_configured,
            "message": (
                "Check your email to verify your Blidx account."
                if settings.EMAIL_VERIFICATION_REQUIRED
                else "Workspace created."
            ),
            "debug_verification_url": email_service.debug_verification_url(token),
        }
    )
    return response


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
    if result.status == "unverified":
        login_rate_limiter.record_success(email)
        raise HTTPException(
            status_code=403,
            detail={
                "code": "email_not_verified",
                "message": "Verify your email before signing in.",
            },
        )
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
        "email_verified_at": user.get("email_verified_at"),
        "email_verified": bool(user.get("email_verified_at")),
    }


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    payload: ChangePasswordRequest,
    background_tasks: BackgroundTasks,
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
    if email_service.delivery_configured:
        background_tasks.add_task(email_service.send_password_changed, updated_user)
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


@router.post("/verification/resend", response_model=AccountEmailResponse)
def resend_verification(
    payload: EmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    email = str(payload.email).strip().lower()
    enforce_account_email_limit(request, email)
    user, token = auth_store.issue_account_token(
        email,
        EMAIL_VERIFICATION_PURPOSE,
        settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES,
    )
    if user and token and email_service.delivery_configured:
        background_tasks.add_task(email_service.send_verification, user, token)
    return {
        "message": "If the account needs verification, a new link has been sent.",
        "delivery_configured": email_service.delivery_configured,
        "debug_url": email_service.debug_verification_url(token),
    }


@router.post("/verify-email", response_model=AccountActionResponse)
def verify_email(payload: VerifyEmailRequest) -> dict:
    user = auth_store.verify_email_token(payload.token)
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_verification_token",
                "message": "This verification link is invalid or expired.",
            },
        )
    return {"message": "Email verified. You can now sign in."}


@router.post("/password/forgot", response_model=AccountEmailResponse)
def forgot_password(
    payload: EmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    email = str(payload.email).strip().lower()
    enforce_account_email_limit(request, email)
    user, token = auth_store.issue_account_token(
        email,
        PASSWORD_RESET_PURPOSE,
        settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    )
    if user and token and email_service.delivery_configured:
        background_tasks.add_task(email_service.send_password_reset, user, token)
    return {
        "message": "If an account exists for that email, a reset link has been sent.",
        "delivery_configured": email_service.delivery_configured,
        "debug_url": email_service.debug_password_reset_url(token),
    }


@router.post("/password/reset", response_model=AccountActionResponse)
def reset_password(
    payload: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    try:
        user = auth_store.reset_password_with_token(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "password_reset_failed", "message": str(exc)},
        ) from exc
    if not user:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_reset_token",
                "message": "This password reset link is invalid or expired.",
            },
        )
    if email_service.delivery_configured:
        background_tasks.add_task(email_service.send_password_changed, user)
    return {
        "message": "Password reset complete. Sign in with your new password."
    }


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
