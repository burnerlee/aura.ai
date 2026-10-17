# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Query and result types for the recommendation engine."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from scraper.models.user import DNARule


class QueryKind(StrEnum):
    CONTENT = "content"
    FACET = "facet"
    STATE = "state"
    PERSONA = "persona"
    CENTROID = "centroid"
    THEME = "theme"  # one of the user's Interest DNA themes


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


class RuleSet(BaseModel):
    """Post-level patterns from the user's Interest DNA, applied while scoring."""

    anti: list[DNARule] = Field(default_factory=list)
    affinities: list[DNARule] = Field(default_factory=list)


class MatchFlag(BaseModel):
    kind: Literal["aversion", "affinity"]
    label: str
    rule_key: str


class MatchInfo(BaseModel):
    """Why a post scored as it did, in terms the UI can show without re-deriving.

    ``percent`` is relative: where this post's fit sits among every candidate the
    engine scored for this request (not the shown list), so "92" means better than 92%
    of what was considered. ``fit`` is the absolute number it was derived from.
    """

    percent: int | None = None
    fit: float
    pool_size: int
    reliable: bool = True  # False when the pool is too small for a stable percentile
    components: dict[str, float] = Field(default_factory=dict)
    top_attribution: str | None = None
    flags: list[MatchFlag] = Field(default_factory=list)


class InsightPostRef(BaseModel):
    """A post the user already reacted to that this one is being compared with."""

    post_id: str
    title: str
    relation: Literal["liked", "skipped"]
    similarity: float
    shared_topics: list[str] = Field(default_factory=list)


class InsightReason(BaseModel):
    kind: Literal[
        "theme",
        "attribution",
        "similar_liked",
        "shared_topics",
        "affinity",
        "caution",
        "similar_skipped",
        "fresh",
        "variety",
        "cold_start",
    ]
    text: str


class MatchInsight(BaseModel):
    """A readable account of why a post is in the user's feed, built only from facts.

    Every sentence comes from something we know: the Interest DNA, the tags, the posts
    the user liked or skipped, the learned rules. Nothing is generated freehand, so a
    referenced post is always a real one the user reacted to.
    """

    headline: str
    summary: str
    reasons: list[InsightReason] = Field(default_factory=list)
    references: list[InsightPostRef] = Field(default_factory=list)


class ScoredPost(BaseModel):
    post_id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)
    per_query_scores: dict[str, float] = Field(default_factory=dict)
    reason: str | None = None
    point_id: str | None = None
    match: MatchInfo | None = None
    insight: MatchInsight | None = None
    # Doc-level embedding, kept so callers can compare this post with others. Internal.
    doc_vector: list[float] | None = Field(default=None, exclude=True)
