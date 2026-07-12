from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET_KEY = "change_this_secret"
PRODUCTION_ENVIRONMENTS = {"production", "staging"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "Blidx Backend"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/blidx"
    USE_DATABASE_STORAGE: bool = False

    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    AUTH_MAX_FAILED_ATTEMPTS: int = 8
    AUTH_LOCKOUT_MINUTES: int = 15
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 20
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS: int = 5
    ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS: int = 900
    ACCOUNT_TOKEN_RESEND_COOLDOWN_SECONDS: int = 60

    EMAIL_PROVIDER: str = "disabled"
    EMAIL_VERIFICATION_REQUIRED: bool = False
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    APP_BASE_URL: str = "http://127.0.0.1:8000"
    EMAIL_FROM: str = ""
    RESEND_API_KEY: str | None = None

    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 1200
    ANTHROPIC_TEMPERATURE: float = 0.7
    OPENAI_API_KEY: str | None = None

    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: str | None = None
    LINKEDIN_REDIRECT_URI: str | None = None
    LINKEDIN_SCOPES: str = "openid profile w_member_social"
    LINKEDIN_API_VERSION: str = "202605"
    LINKEDIN_TOKEN_ENCRYPTION_KEY: str | None = None
    LINKEDIN_OAUTH_STATE_EXPIRE_MINUTES: int = 10

    SEARCH_API_KEY: str | None = None

    ADMIN_USERNAME: str | None = None
    ADMIN_PASSWORD: str | None = None

settings = Settings()


def is_production_environment(config: Settings = settings) -> bool:
    return config.ENVIRONMENT.strip().lower() in PRODUCTION_ENVIRONMENTS


def production_configuration_errors(config: Settings = settings) -> list[str]:
    if not is_production_environment(config):
        return []

    errors: list[str] = []
    if config.DEBUG:
        errors.append("DEBUG must be false")
    if not config.USE_DATABASE_STORAGE:
        errors.append("USE_DATABASE_STORAGE must be true")
    if not config.DATABASE_URL or "localhost" in config.DATABASE_URL.lower():
        errors.append("DATABASE_URL must point to a production database")
    if (
        config.JWT_SECRET_KEY == DEFAULT_JWT_SECRET_KEY
        or len(config.JWT_SECRET_KEY) < 32
    ):
        errors.append(
            "JWT_SECRET_KEY must be a unique value of at least 32 characters"
        )
    positive_security_values = {
        "ACCESS_TOKEN_EXPIRE_MINUTES": config.ACCESS_TOKEN_EXPIRE_MINUTES,
        "AUTH_MAX_FAILED_ATTEMPTS": config.AUTH_MAX_FAILED_ATTEMPTS,
        "AUTH_LOCKOUT_MINUTES": config.AUTH_LOCKOUT_MINUTES,
        "LOGIN_RATE_LIMIT_ATTEMPTS": config.LOGIN_RATE_LIMIT_ATTEMPTS,
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS": config.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        "ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS": (
            config.ACCOUNT_EMAIL_RATE_LIMIT_ATTEMPTS
        ),
        "ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS": (
            config.ACCOUNT_EMAIL_RATE_LIMIT_WINDOW_SECONDS
        ),
        "ACCOUNT_TOKEN_RESEND_COOLDOWN_SECONDS": (
            config.ACCOUNT_TOKEN_RESEND_COOLDOWN_SECONDS
        ),
        "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES": (
            config.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES
        ),
        "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES": (
            config.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        ),
    }
    for name, value in positive_security_values.items():
        if value <= 0:
            errors.append(f"{name} must be greater than zero")

    email_provider = config.EMAIL_PROVIDER.strip().lower()
    if email_provider not in {"disabled", "resend"}:
        errors.append("EMAIL_PROVIDER must be disabled or resend in production")
    if email_provider == "resend":
        if not config.RESEND_API_KEY:
            errors.append("RESEND_API_KEY is required when EMAIL_PROVIDER is resend")
        if not config.EMAIL_FROM.strip():
            errors.append("EMAIL_FROM is required when EMAIL_PROVIDER is resend")
        if not config.APP_BASE_URL.startswith("https://"):
            errors.append("APP_BASE_URL must use HTTPS when email delivery is enabled")
    if config.EMAIL_VERIFICATION_REQUIRED and email_provider != "resend":
        errors.append(
            "EMAIL_VERIFICATION_REQUIRED needs EMAIL_PROVIDER=resend in production"
        )

    linkedin_values = [config.LINKEDIN_CLIENT_ID, config.LINKEDIN_CLIENT_SECRET]
    if any(linkedin_values) and not all(linkedin_values):
        errors.append("LinkedIn client ID and secret must be configured together")
    if all(linkedin_values):
        linkedin_scopes = set(config.LINKEDIN_SCOPES.split())
        required_scopes = {"openid", "profile", "w_member_social"}
        if not required_scopes.issubset(linkedin_scopes):
            errors.append(
                "LINKEDIN_SCOPES must include openid, profile, and w_member_social"
            )
        if (
            not config.LINKEDIN_REDIRECT_URI
            or not config.LINKEDIN_REDIRECT_URI.startswith("https://")
        ):
            errors.append("LinkedIn redirect URI must use HTTPS")
        if (
            not config.LINKEDIN_TOKEN_ENCRYPTION_KEY
            or len(config.LINKEDIN_TOKEN_ENCRYPTION_KEY) < 32
        ):
            errors.append(
                "LINKEDIN_TOKEN_ENCRYPTION_KEY must be at least 32 characters"
            )
        elif config.LINKEDIN_TOKEN_ENCRYPTION_KEY == config.JWT_SECRET_KEY:
            errors.append(
                "LINKEDIN_TOKEN_ENCRYPTION_KEY must differ from JWT_SECRET_KEY"
            )

    return errors


def validate_runtime_configuration(config: Settings = settings) -> None:
    errors = production_configuration_errors(config)
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


def security_configuration_status(config: Settings = settings) -> str:
    if not is_production_environment(config):
        return "development"
    return "hardened" if not production_configuration_errors(config) else "unsafe"
