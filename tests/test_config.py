import pytest

from app.core.config import (
    DEFAULT_JWT_SECRET_KEY,
    production_configuration_errors,
    security_configuration_status,
    settings,
    validate_runtime_configuration,
)


def production_settings(**updates):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "USE_DATABASE_STORAGE": True,
        "DATABASE_URL": "postgresql+psycopg2://blidx:password@db.example.com/blidx",
        "JWT_SECRET_KEY": "j" * 48,
        "LINKEDIN_CLIENT_ID": "linkedin-client",
        "LINKEDIN_CLIENT_SECRET": "linkedin-secret",
        "LINKEDIN_REDIRECT_URI": "https://app.example.com/auth/linkedin/callback",
        "LINKEDIN_TOKEN_ENCRYPTION_KEY": "e" * 48,
    }
    values.update(updates)
    return settings.model_copy(update=values)


def test_local_configuration_allows_development_defaults():
    local = settings.model_copy(
        update={
            "ENVIRONMENT": "local",
            "JWT_SECRET_KEY": DEFAULT_JWT_SECRET_KEY,
        }
    )

    assert production_configuration_errors(local) == []
    assert security_configuration_status(local) == "development"
    validate_runtime_configuration(local)


def test_production_configuration_rejects_unsafe_defaults():
    unsafe = production_settings(
        DEBUG=True,
        USE_DATABASE_STORAGE=False,
        DATABASE_URL="postgresql://postgres:postgres@localhost:5432/blidx",
        JWT_SECRET_KEY=DEFAULT_JWT_SECRET_KEY,
        LINKEDIN_REDIRECT_URI="http://localhost/auth/linkedin/callback",
        LINKEDIN_TOKEN_ENCRYPTION_KEY=None,
    )

    errors = production_configuration_errors(unsafe)

    assert "DEBUG must be false" in errors
    assert "USE_DATABASE_STORAGE must be true" in errors
    assert "DATABASE_URL must point to a production database" in errors
    assert any("JWT_SECRET_KEY" in error for error in errors)
    assert "LinkedIn redirect URI must use HTTPS" in errors
    assert any("LINKEDIN_TOKEN_ENCRYPTION_KEY" in error for error in errors)
    assert security_configuration_status(unsafe) == "unsafe"
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        validate_runtime_configuration(unsafe)


def test_production_configuration_accepts_hardened_values():
    secure = production_settings()

    assert production_configuration_errors(secure) == []
    assert security_configuration_status(secure) == "hardened"
    validate_runtime_configuration(secure)


def test_production_configuration_requires_separate_encryption_keys():
    shared_secret = "s" * 48
    unsafe = production_settings(
        JWT_SECRET_KEY=shared_secret,
        LINKEDIN_TOKEN_ENCRYPTION_KEY=shared_secret,
    )

    assert "LINKEDIN_TOKEN_ENCRYPTION_KEY must differ from JWT_SECRET_KEY" in (
        production_configuration_errors(unsafe)
    )


def test_production_configuration_requires_linkedin_identity_and_posting_scopes():
    unsafe = production_settings(LINKEDIN_SCOPES="openid profile")

    assert "LINKEDIN_SCOPES must include openid, profile, and w_member_social" in (
        production_configuration_errors(unsafe)
    )


def test_production_configuration_rejects_disabled_login_protection():
    unsafe = production_settings(
        ACCESS_TOKEN_EXPIRE_MINUTES=0,
        AUTH_MAX_FAILED_ATTEMPTS=0,
        AUTH_LOCKOUT_MINUTES=0,
        LOGIN_RATE_LIMIT_ATTEMPTS=0,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=0,
        ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS=0,
        ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS=0,
        ACCOUNT_TOKEN_RESEND_COOLDOWN_SECONDS=0,
        EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES=0,
        PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=0,
    )

    errors = production_configuration_errors(unsafe)

    assert "ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero" in errors
    assert "AUTH_MAX_FAILED_ATTEMPTS must be greater than zero" in errors
    assert "AUTH_LOCKOUT_MINUTES must be greater than zero" in errors
    assert "LOGIN_RATE_LIMIT_ATTEMPTS must be greater than zero" in errors
    assert "LOGIN_RATE_LIMIT_WINDOW_SECONDS must be greater than zero" in errors
    assert "ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS must be greater than zero" in errors
    assert "ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS must be greater than zero" in errors
    assert "ACCOUNT_TOKEN_RESEND_COOLDOWN_SECONDS must be greater than zero" in errors
    assert "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES must be greater than zero" in errors
    assert "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES must be greater than zero" in errors


def test_production_email_verification_requires_resend_configuration():
    unsafe = production_settings(
        EMAIL_PROVIDER="console",
        EMAIL_VERIFICATION_REQUIRED=True,
        RESEND_API_KEY=None,
        APP_BASE_URL="http://localhost:8000",
    )

    errors = production_configuration_errors(unsafe)

    assert "EMAIL_PROVIDER must be disabled or resend in production" in errors
    assert (
        "EMAIL_VERIFICATION_REQUIRED needs EMAIL_PROVIDER=resend in production"
        in errors
    )


def test_production_resend_configuration_is_accepted():
    secure = production_settings(
        EMAIL_PROVIDER="resend",
        EMAIL_VERIFICATION_REQUIRED=True,
        RESEND_API_KEY="resend-secret-key",
        EMAIL_FROM="Blidx <security@blidx.example>",
        APP_BASE_URL="https://app.blidx.example",
    )

    assert production_configuration_errors(secure) == []


def test_production_resend_rejects_missing_sender_key_and_https_base_url():
    unsafe = production_settings(
        EMAIL_PROVIDER="resend",
        RESEND_API_KEY=None,
        EMAIL_FROM="",
        APP_BASE_URL="http://app.blidx.example",
    )

    errors = production_configuration_errors(unsafe)

    assert "RESEND_API_KEY is required when EMAIL_PROVIDER is resend" in errors
    assert "EMAIL_FROM is required when EMAIL_PROVIDER is resend" in errors
    assert "APP_BASE_URL must use HTTPS when email delivery is enabled" in errors
