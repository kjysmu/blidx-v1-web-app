from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "Blidx Backend"
    ENVIRONMENT: str = "local"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/blidx"

    JWT_SECRET_KEY: str = "change_this_secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = 1200
    ANTHROPIC_TEMPERATURE: float = 0.7
    OPENAI_API_KEY: str | None = None

    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: str | None = None
    LINKEDIN_REDIRECT_URI: str | None = None
    LINKEDIN_SCOPES: str = "openid profile email w_member_social"

    SEARCH_API_KEY: str | None = None

    ADMIN_USERNAME: str | None = None
    ADMIN_PASSWORD: str | None = None

settings = Settings()
