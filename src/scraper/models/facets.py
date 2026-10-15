# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""LLM-extracted facet schema for posts (style / emotion / personality appeal)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmotionScores(BaseModel):
    sadness: float = 0.0
    fear: float = 0.0
    excitement: float = 0.0
    disgust: float = 0.0
    contentment: float = 0.0
    awe: float = 0.0
    anger: float = 0.0
    amusement: float = 0.0

    def primary(self) -> str:
        scores = self.model_dump()
        return max(scores, key=scores.get)


class PersonalityAppeal(BaseModel):
    """Big Five appeal scores in [0, 1]."""

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    neuroticism: float = 0.5
    agreeableness: float = 0.5


class PostFacets(BaseModel):
    topics: list[str] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)
    emotion: EmotionScores = Field(default_factory=EmotionScores)
    personality_appeal: PersonalityAppeal = Field(default_factory=PersonalityAppeal)
    reading_level: str | None = None
    audience: str | None = None
    one_line_appeal: str | None = None

    def to_embed_text(self) -> str:
        emotion_primary = self.emotion.primary()
        parts = [
            f"topics: {', '.join(self.topics)}" if self.topics else "",
            f"style: {', '.join(self.style)}" if self.style else "",
            f"emotion: {emotion_primary}",
            f"audience: {self.audience}" if self.audience else "",
            f"reading_level: {self.reading_level}" if self.reading_level else "",
            f"appeal: {self.one_line_appeal}" if self.one_line_appeal else "",
        ]
        return " | ".join(p for p in parts if p)
