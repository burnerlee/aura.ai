# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Query and result types for the recommendation engine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class QueryKind(StrEnum):
    CONTENT = "content"
    FACET = "facet"
    STATE = "state"
    PERSONA = "persona"
    CENTROID = "centroid"


class QueryVector(BaseModel):
    vector: list[float]
    weight: float = 1.0
    kind: QueryKind = QueryKind.CONTENT
    label: str | None = None


class QuerySet(BaseModel):
    vectors: list[QueryVector] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.vectors)


class Filters(BaseModel):
    sources: list[str] | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None
    authors: list[str] | None = None
    muted_authors: list[str] | None = None
    muted_sources: list[str] | None = None
    published_after: float | None = None
    language: str | None = None
    max_words: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ScoredPost(BaseModel):
    post_id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)
    per_query_scores: dict[str, float] = Field(default_factory=dict)
    reason: str | None = None
    point_id: str | None = None
