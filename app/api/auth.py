from fastapi import APIRouter
from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse

router = APIRouter()


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest):
    # TODO Day 3–4:
    # 1. Check email not used
    # 2. Hash password
    # 3. Create user
    # 4. Return JWT
    return {
        "access_token": "placeholder_token",
        "token_type": "bearer",
        "user_id": "placeholder_user_id",
    }


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    # TODO Day 3–4:
    # 1. Find user by email
    # 2. Verify password
    # 3. Return JWT
    return {
        "access_token": "placeholder_token",
        "token_type": "bearer",
        "user_id": "placeholder_user_id",
    }
