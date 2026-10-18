# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Request bodies for the recommendation API (module-level for FastAPI)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from scraper.models.user import EventType, FeedbackReason


class SearchRequest(BaseModel):
    query: str
    k: int = 10
    sources: list[str] | None = None
    explain: bool = False


class EventIn(BaseModel):
    post_id: str | None = None
    event: EventType
    strength: int | None = None
    hold_ms: int | None = None
    reason: FeedbackReason | None = None
    dwell_ms: int | None = None
    visible_ms: int | None = None
    scroll_depth: float | None = None
    completed: bool | None = None
    read_ratio: float | None = None
    text: str | None = None
    pair_post_id: str | None = None
    # What the card showed when the user reacted, so feedback can be weighted by how
    # confident the match was and the culprit (what pulled the post in) can be recorded.
    match_percent: float | None = None
    matched_label: str | None = None


class EventsRequest(BaseModel):
    events: list[EventIn] = Field(default_factory=list)


class TuneRequest(BaseModel):
    text: str


class OnboardRequest(BaseModel):
    free_text: str | None = None
    seed_post_ids: list[str] = Field(default_factory=list)


class AuraChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AuraProfileDraftIn(BaseModel):
    prompt: str = ""
    topics: list[str] = Field(default_factory=list)
    anti_topics: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    theme_weights: dict[str, float] = Field(default_factory=dict)
    preferred_styles: list[str] = Field(default_factory=list)
    preferred_emotions: list[str] = Field(default_factory=list)


class AuraChatRequest(BaseModel):
    messages: list[AuraChatMessageIn] = Field(default_factory=list)
    known_themes: list[str] = Field(default_factory=list)
    apply: bool = False  # when true, persist persona from profile or ready turn
    profile: AuraProfileDraftIn | None = None


class DNAImportRequest(BaseModel):
    """The Interest DNA a browser kept in localStorage before it moved server-side."""

    vector: dict[str, float] = Field(default_factory=dict)
    prompt: str = ""
    excluded_categories: list[str] = Field(default_factory=list)


class ImportUrlRequest(BaseModel):
    """Import (fetch) a URL on-demand so it can be embedded and recommended."""

    url: str
    # When true, embed synchronously before responding (use sparingly; slower).
    wait_for_embed: bool = False


class LiveSearchRequest(BaseModel):
    """Realtime search: discover fresh links, import, and (optionally) embed."""

    query: str
    k: int = 10
    # How many links to pull from Google News for this request (upper bound).
    discover_k: int = 20
    # Only consider "fresh" news; implemented as a Google query operator (when:Nh).
    max_age_hours: int = 24
    # When true, block to embed newly imported links before returning.
    wait_for_embed: bool = False
