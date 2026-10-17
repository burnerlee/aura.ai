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
    mongo_users_collection: str = "users"
    mongo_interactions_collection: str = "interactions"
    mongo_tags_collection: str = "tags"
    mongo_accounts_collection: str = "accounts"

    http_timeout_seconds: float = 30.0
    http_user_agent: str = "content-scraper/0.1 (+https://github.com/devrev/data)"
    request_delay_seconds: float = 0.5
    log_level: str = "INFO"

    # Gemini (free-tier — preferred for user-side inference: onboard / persona / rerank)
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_llm_model: str = "gemini-2.5-flash"
    embedding_dim: int = 768
    embed_concurrency: int = 4
    facets_enabled: bool = True
    embed_images: bool = False

    # LiteLLM (preferred for indexing embeds + facet extraction)
    litellm_api_key: str | None = None
    litellm_api_base: str | None = None
    # The whole corpus, every user vector and every query must share this one model.
    # Changing it requires re-embedding everything (`make reembed`).
    litellm_embedding_model: str = "openai/text-embedding-3-small"
    litellm_llm_model: str = "openai/gemini-2.5-flash"
    # Upper bound only. Thinking models spend part of it on reasoning before the JSON.
    llm_max_output_tokens: int = 8192

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "posts"

    # Chunking
    chunk_words: int = 300
    chunk_overlap_words: int = 40
    max_chunks_per_post: int = 32
    min_body_words: int = 40

    # Query engine
    filter_k: int = 64
    # Share of the fit score taken from whole-post (doc) similarity vs chunk MaxSim.
    doc_similarity_weight: float = 0.5
    mmr_lambda: float = 0.85
    author_diversity_cap: int = 3
    # Largest share of one recommendation slate a single source may take, so one
    # connector (e.g. Substack) cannot crowd out the others (e.g. Reddit).
    source_max_share: float = 0.6
    recency_half_life_days: float = 30.0
    # How much of the score recency can take away (0 = ignore age, 1 = full decay).
    recency_weight: float = 0.1
    negative_penalty_scale: float = 0.35

    # Profile
    interest_centroid_k: int = 6
    persona_refresh_every: int = 10
    weight_version: str = "default_v1"

    # Canonical tag vocabulary: labels closer than this cosine collapse into one tag.
    tag_cluster_threshold: float = 0.85
    # Looser cosine for mapping a free-form label onto a (coarse) theme centroid.
    theme_resolve_threshold: float = 0.75

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Shared secret the Express BFF sends on BFF-only routes (account linking).
    aura_internal_token: str | None = None

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
