from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

from app.auth_store import auth_store
from app.core.security import create_access_token, decode_access_token
from app.demo_store import demo_store
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse
from app.integrations.linkedin import LinkedInClient

router = APIRouter()


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
def linkedin_callback(code: str | None = None, error: str | None = None):
    if error:
        return RedirectResponse(url=f"/?linkedin=error")
    if not code:
        return RedirectResponse(url="/?linkedin=missing_code")

    linkedin = LinkedInClient()
    token = linkedin.exchange_code_for_token(code)
    profile = linkedin.get_userinfo(token["access_token"])
    demo_store.store_linkedin_connection(token, profile)
    return RedirectResponse(url="/?linkedin=connected")
