# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Canonical tag vocabulary models (topics / styles derived from post facets)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TagKind(StrEnum):
    TOPIC = "topic"  # fine-grained subject of a post ("Federal Reserve")
    STYLE = "style"  # how it is written ("analytical", "listicle")
    THEME = "theme"  # coarse group of topics; the unit Interest DNA is keyed by


class Tag(BaseModel):
    """One canonical label plus the raw facet labels that collapse into it.

    ``id`` is ``<kind>:<slug of canonical label>`` so it is human-readable and stable
    as long as the canonical label does not change. When a rebuild retires an id
    because its label merged into another tag, ``merged_into`` keeps old references
    (user Interest DNA keys) resolvable.
    """

    id: str
    kind: TagKind
    label: str
    aliases: list[str] = Field(default_factory=list)
    doc_count: int = 0
    embedding: list[float] = Field(default_factory=list)
    merged_into: str | None = None
    parent_id: str | None = None  # topic tag -> its theme tag
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(mode="python")
        data["_id"] = data.pop("id")
        return data

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Tag:
        data = {k: v for k, v in doc.items() if k != "_id"}
        data["id"] = doc["_id"]
        return cls.model_validate(data)

    def to_public(self) -> dict[str, Any]:
        """API shape: no embedding vector."""
        return self.model_dump(mode="json", exclude={"embedding"})

    def ref(self) -> TagRef:
        return TagRef(id=self.id, label=self.label, kind=self.kind)


class TagRef(BaseModel):
    """Compact tag reference stored on each post (``canonical_tags``)."""

    id: str
    label: str
    kind: TagKind
