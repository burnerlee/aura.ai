# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""User profile, persona, and interaction models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

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


class DNARuleKind(StrEnum):
    TOPIC = "topic"
    STYLE = "style"
    EMOTION = "emotion"
    AUTHOR = "author"
    SOURCE = "source"
    LENGTH = "length"
    READING_LEVEL = "reading_level"


class DNARuleSource(StrEnum):
    CHAT = "chat"  # stated by the user in the Aura conversation
    LEARNED = "learned"  # mined from feedback, not yet confirmed
    CONFIRMED = "confirmed"  # learned or proposed, then accepted by the user


class DNARule(BaseModel):
    """A post-level pattern the user likes (affinity) or avoids (anti)."""

    kind: DNARuleKind
    key: str  # tag id for topic/style, otherwise the raw value (author name, ...)
    label: str | None = None
    strength: float = 1.0  # 0..1
    source: DNARuleSource = DNARuleSource.CHAT
    evidence_ids: list[str] = Field(default_factory=list)


class InterestDNA(BaseModel):
    """Server-owned Interest DNA: what the UI ring, rail and chips render.

    ``weights`` is a distribution over canonical tag ids (``topic:practical-ai``) that
    sums to ~100. Themes the corpus has no tag for yet are kept under ``custom:<slug>``
    so the user's stated intent is never dropped. ``version`` is bumped on every write
    and used for optimistic concurrency; 0 means "never populated".
    """

    weights: dict[str, float] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    anti: list[DNARule] = Field(default_factory=list)
    affinities: list[DNARule] = Field(default_factory=list)
    prompt: str = ""
    # "<kind>:<key>" of rules the user removed; mining must not propose them again.
    dismissed: list[str] = Field(default_factory=list)
    version: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NoticedAttr(BaseModel):
    """An attribute of a post the user just reacted to, offered back as a one-tap chip."""

    kind: DNARuleKind
    key: str
    label: str
    seen: int  # posts with this attribute the user has reacted to
    negative: int  # ...of which skipped / banished


class DNAPatch(BaseModel):
    """Manual edit of the DNA (drag a slice, delete an anti-pattern, ...)."""

    base_version: int
    set_weights: dict[str, float] = Field(default_factory=dict)  # key -> target %
    remove_weights: list[str] = Field(default_factory=list)
    add_anti: list[DNARule] = Field(default_factory=list)
    remove_anti: list[str] = Field(default_factory=list)  # rule keys
    prompt: str | None = None


class AuraConversationMessage(BaseModel):
    """Stored Aura personalization chat turn (not shown in the UI)."""

    role: Literal["user", "assistant"]
    content: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    # What the UI showed when the user reacted (client-reported).
    match_percent: float | None = None
    matched_label: str | None = None  # top attribution on the card, i.e. what pulled it in
    # Server-built facets of the post at feedback time; the input to pattern mining.
    snapshot: dict[str, Any] | None = None
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
    dna: InterestDNA = Field(default_factory=InterestDNA)
    positive_ids: list[str] = Field(default_factory=list)
    negative_ids: list[str] = Field(default_factory=list)
    seen_ids: list[str] = Field(default_factory=list)
    exclude_near_ids: list[str] = Field(default_factory=list)
    # Hidden from the chat UI; kept so Aura can resume context later.
    aura_conversation: list[AuraConversationMessage] = Field(default_factory=list)
    persona_version: int = 0
    interaction_count_since_persona: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> UserProfile:
        data = {k: v for k, v in doc.items() if k != "_id"}
        return cls.model_validate(data)
