# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Canonical post document stored in MongoDB — shared by all connectors."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EmbeddingStatus(str, Enum):
    """Lifecycle flag for future vector / recommendation pipeline."""

    PENDING = "pending"
    READY = "ready"
    SKIPPED = "skipped"
    FAILED = "failed"


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def _prune(value: Any) -> Any:
    """Recursively drop null / blank / empty containers for clean Mongo docs."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            pruned = _prune(item)
            if _is_empty(pruned):
                continue
            cleaned[key] = pruned
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            pruned = _prune(item)
            if _is_empty(pruned):
                continue
            cleaned_list.append(pruned)
        return cleaned_list
    if isinstance(value, str):
        return value.strip()
    return value


class Author(BaseModel):
    name: str | None = None
    external_id: str | None = None
    url: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentDocument(BaseModel):
    """Uniform record written by every connector into the ``posts`` collection.

    Unique in MongoDB by ``(source, external_id)``.
    """

    # Identity
    source: str
    external_id: str
    url: str | None = None
    embed_url: str | None = None
    canonical_url: str | None = None

    # Content
    title: str | None = None
    subtitle: str | None = None
    content: str | None = None
    content_html: str | None = None
    content_text: str | None = None
    summary: str | None = None
    language: str | None = None

    # People / media
    author: Author | None = None
    cover_image_url: str | None = None
    media_urls: list[str] = Field(default_factory=list)

    # Classification
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    audience: str | None = None

    # Timestamps
    published_at: datetime | None = None
    updated_at: datetime | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Engagement / source extras
    word_count: int | None = None
    reaction_count: int | None = None
    comment_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Intentionally not persisted by default — huge and noisy in Compass.
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    # Future vector / recommendation hooks
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    embedding_id: str | None = None
    embedding_model: str | None = None

    def mongo_key(self) -> dict[str, str]:
        return {"source": self.source, "external_id": self.external_id}

    def to_mongo(self) -> dict[str, Any]:
        payload = self.model_dump(mode="python", exclude_none=True, exclude={"raw"})
        cleaned = _prune(payload)
        # Always keep identity keys even if somehow empty (shouldn't happen)
        cleaned["source"] = self.source
        cleaned["external_id"] = self.external_id
        return cleaned

    @property
    def scrape_source_id(self) -> str:
        """Handle/URL to scrape related content for a publication-like row."""
        subdomain = self.metadata.get("subdomain")
        if subdomain:
            return str(subdomain)
        if self.url:
            return self.url
        return self.external_id
