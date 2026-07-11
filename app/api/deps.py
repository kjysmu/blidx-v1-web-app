from fastapi import Depends, Header, HTTPException

from app.auth_store import auth_store
from app.core.security import decode_access_token
from app.demo_store import current_user_id, demo_store


def use_request_user(authorization: str | None = Header(default=None)) -> dict | None:
    current_user_id.set(None)
    if not authorization or not authorization.lower().startswith("bearer "):
        return None

    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_access_token(token)
    if not user_id:
        return None

    user = auth_store.get_user(user_id)
    if not user:
        return None

    current_user_id.set(user["id"])
    demo_store.ensure_user_state(user)
    current_user_id.set(user["id"])
    return user


def require_request_user(user: dict | None = Depends(use_request_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to connect LinkedIn")
    return user
