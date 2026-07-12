from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    user_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class RevokeSessionsRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: EmailStr
    user_name: str | None = None
