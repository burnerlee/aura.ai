# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""User profile, persona, and interaction models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    IMPRESSION = "impression"
    OPEN = "open"
    DWELL = "dwell"
    CLICK_THROUGH = "click_through"
    SHARE = "share"
    LIKE = "like"
    NOT_INTERESTED = "not_interested"
    SAVE = "save"
    FOLLOW_AUTHOR = "follow_author"
    MUTE_AUTHOR = "mute_author"
    MUTE_SOURCE = "mute_source"
    PAIRWISE = "pairwise"
    TUNE = "tune"
    EXPLANATION_FEEDBACK = "explanation_feedback"


class FeedbackReason(StrEnum):
    TOPIC = "topic"
    ALREADY_KNOW = "already_know"
    TOO_LONG = "too_long"
    LOW_QUALITY = "low_quality"
    AUTHOR = "author"
    TONE = "tone"
    STYLE = "style"
    DEPTH = "depth"


class BigFive(BaseModel):
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    neuroticism: float = 0.5
    agreeableness: float = 0.5


class Persona(BaseModel):
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    anti_topics: list[str] = Field(default_factory=list)
    preferred_styles: list[str] = Field(default_factory=list)
    preferred_emotions: list[str] = Field(default_factory=list)
    big_five: BigFive = Field(default_factory=BigFive)
    reading_level: str | None = None
    max_words: int | None = None
    muted_authors: list[str] = Field(default_factory=list)
    muted_sources: list[str] = Field(default_factory=list)


class InterestCentroid(BaseModel):
    vector: list[float]
    weight: float = 1.0
    label: str | None = None


class Interaction(BaseModel):
    user_id: str
    post_id: str | None = None
    event: EventType
    strength: int | None = None  # 1 or 2 for like / not_interested
    hold_ms: int | None = None  # stored but not used by live weight table
    reason: FeedbackReason | None = None
    dwell_ms: int | None = None
    visible_ms: int | None = None
    scroll_depth: float | None = None
    completed: bool | None = None
    read_ratio: float | None = None
    text: str | None = None  # tune / explanation_feedback free text
    pair_post_id: str | None = None  # winner or loser counterpart for pairwise
    weight: float | None = None
    weight_version: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_none=True)


class UserProfile(BaseModel):
    user_id: str
    persona: Persona = Field(default_factory=Persona)
    persona_vector: list[float] | None = None
    state_vector: list[float] | None = None
    interest_centroids: list[InterestCentroid] = Field(default_factory=list)
    positive_ids: list[str] = Field(default_factory=list)
    negative_ids: list[str] = Field(default_factory=list)
    seen_ids: list[str] = Field(default_factory=list)
    exclude_near_ids: list[str] = Field(default_factory=list)
    persona_version: int = 0
    interaction_count_since_persona: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> UserProfile:
        data = {k: v for k, v in doc.items() if k != "_id"}
        return cls.model_validate(data)
