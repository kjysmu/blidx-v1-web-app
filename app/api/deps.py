from fastapi import Depends, Header, HTTPException, Request

from app.auth_store import auth_store
from app.core.security import (
    AccessTokenError,
    AccessTokenExpiredError,
    decode_access_token,
)
from app.demo_store import current_user_id, demo_store


def _set_session_error(request: Request, code: str, message: str) -> None:
    request.state.session_error = {"code": code, "message": message}


def use_request_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict | None:
    current_user_id.set(None)
    request.state.session_error = None
    if not authorization or not authorization.lower().startswith("bearer "):
        _set_session_error(request, "missing_session", "Sign in to continue.")
        return None

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token)
    except AccessTokenExpiredError:
        _set_session_error(
            request,
            "session_expired",
            "Your session expired. Please sign in again.",
        )
        return None
    except AccessTokenError:
        _set_session_error(
            request,
            "invalid_session",
            "Your session is invalid. Please sign in again.",
        )
        return None

    user = auth_store.get_user(str(claims["user_id"]))
    if not user:
        _set_session_error(
            request,
            "invalid_session",
            "Your account could not be found. Please sign in again.",
        )
        return None

    if int(user.get("session_version", 1)) != int(claims["session_version"]):
        _set_session_error(
            request,
            "session_revoked",
            "This session was signed out. Please sign in again.",
        )
        return None

    current_user_id.set(user["id"])
    demo_store.ensure_user_state(user)
    current_user_id.set(user["id"])
    return user


def require_request_user(
    request: Request,
    user: dict | None = Depends(use_request_user),
) -> dict:
    if not user:
        detail = request.state.session_error or {
            "code": "invalid_session",
            "message": "Sign in to continue.",
        }
        raise HTTPException(status_code=401, detail=detail)
    return user
