# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Typed embedding input produced by content adapters from raw Mongo docs."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SkipReason(StrEnum):
    """Why a raw Mongo doc should not be embedded."""

    NO_BODY = "no_body"
    TOO_SHORT = "too_short"
    NOT_A_POST = "not_a_post"
    UNSUPPORTED_LANGUAGE = "unsupported_language"


class EmbeddableContent(BaseModel):
    """Resolved, typed view of a post for the embedding / recommendation pipeline.

    Downstream code (chunker, facets, Qdrant payload) must only consume this
    model — never raw Mongo dicts.
    """

    post_id: str
    source: str
    external_id: str
    title: str | None = None
    subtitle: str | None = None
    summary: str | None = None
    body_text: str
    author_name: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    word_count: int | None = None
    image_urls: list[str] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)

    def head_text(self) -> str:
        parts = [p for p in (self.title, self.subtitle, self.summary) if p and p.strip()]
        return "\n".join(parts).strip()

    @property
    def content_hash(self) -> str:
        payload = f"{self.title or ''}\n{self.body_text}".encode()
        return hashlib.sha256(payload).hexdigest()

    def payload(self) -> dict[str, Any]:
        """Qdrant payload subset (scalars / short lists only)."""
        published_epoch: float | None = None
        if self.published_at is not None:
            published_epoch = self.published_at.timestamp()
        return {
            "post_id": self.post_id,
            "source": self.source,
            "external_id": self.external_id,
            "title": self.title,
            "url": self.url,
            "author_name": self.author_name,
            "categories": self.categories,
            "tags": self.tags,
            "published_at": published_epoch,
            "word_count": self.word_count or len(self.body_text.split()),
            "language": self.language,
        }
