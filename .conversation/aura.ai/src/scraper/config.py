# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Application settings loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str = "scraper"
    mongo_password: str = "scraper"
    mongo_db: str = "content_scraper"
    mongo_collection: str = "posts"
    mongo_uri: str | None = None

    http_timeout_seconds: float = 30.0
    http_user_agent: str = "content-scraper/0.1 (+https://github.com/devrev/data)"
    request_delay_seconds: float = 0.5
    log_level: str = "INFO"

    def build_mongo_uri(self) -> str:
        if self.mongo_uri:
            return self.mongo_uri
        return (
            f"mongodb://{self.mongo_user}:{self.mongo_password}"
            f"@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}?authSource=admin"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
