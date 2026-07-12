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


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: EmailStr
    user_name: str | None = None
    email_verified: bool


class RegistrationResponse(BaseModel):
    access_token: str | None = None
    token_type: str | None = None
    user_id: str
    email: EmailStr
    user_name: str | None = None
    email_verified: bool
    verification_required: bool
    delivery_configured: bool
    message: str
    debug_verification_url: str | None = None


class AccountEmailResponse(BaseModel):
    message: str
    delivery_configured: bool
    debug_url: str | None = None


class AccountActionResponse(BaseModel):
    message: str
