from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CP Hub Backend"
    app_env: str = "local"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cp_hub"
    backend_cors_origins: list[str] = Field(default_factory=list)
    auth_jwt_secret: str = "local-development-only-secret-change-me"
    auth_access_token_minutes: int = 15
    auth_refresh_token_days: int = 14
    auth_refresh_cookie_secure: bool = False
    auth_setup_token_minutes: int = 60 * 24
    frontend_base_url: str = "http://localhost:5173"
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    notify_hub_base_url: str | None = None
    notify_hub_api_key: str | None = None
    notify_hub_webhook_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
