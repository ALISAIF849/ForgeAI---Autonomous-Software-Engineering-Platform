from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str
    redis_url: str

    jwt_secret_key: str = "dev-insecure-change-me-32-bytes-min"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Comma-separated in .env (CORS_ALLOWED_ORIGINS=http://a,http://b), matching
    # docs/engineering/06-environment-configuration.md's .env.example — kept as a
    # plain str field (aliased back to the real env var name) rather than list[str],
    # because pydantic-settings always tries a JSON decode first for complex-typed
    # env values, before any validator gets a chance to run — confirmed by hitting
    # the resulting SettingsError against a real .env.local, not assumed. Splitting
    # in a plain property sidesteps that decoding path entirely.
    cors_allowed_origins_raw: str = Field(
        default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS"
    )
    rate_limit_default_per_minute: int = 60

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
