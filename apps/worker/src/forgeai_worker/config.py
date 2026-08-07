"""A small Settings class of its own, not shared with apps/api's — the two
are independent deployable processes that happen to read overlapping
env vars (see .env.example's own comment on why the *files* stay in sync),
not one process's config reused by another. apps/api's Settings carries
JWT/CORS/rate-limit fields this process has no use for; this one carries
poll_interval_seconds, which apps/api has no use for. Sharing the class would
mean each process depending on config fields it doesn't need and can't
sensibly provide defaults for.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str

    # How long to sleep after finding the queue empty before polling again.
    # Not how long a single execution takes to process — claim_next()/
    # advance() calls themselves aren't throttled by this.
    poll_interval_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
