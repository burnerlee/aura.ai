# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""FastAPI app: search, similar, feed, events, profile, onboard, persona."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from scraper.models.user import EventType, FeedbackReason, Interaction
from scraper.profile.service import UserProfileService
from scraper.query.engine import RecommendationEngine
from scraper.query.types import Filters


def create_app() -> FastAPI:
    app = FastAPI(title="Content Recommendation API", version="0.1.0")
    engine = RecommendationEngine()
    profiles = UserProfileService(engine=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    class SearchRequest(BaseModel):
        query: str
        k: int = 10
        sources: list[str] | None = None
        explain: bool = False

    @app.post("/search")
    def search(body: SearchRequest) -> list[dict[str, Any]]:
        filters = Filters(sources=body.sources) if body.sources else None
        results = engine.search(body.query, k=body.k, filters=filters, explain=body.explain)
        return [r.model_dump() for r in results]

    @app.get("/posts/{post_id}/similar")
    def similar(post_id: str, k: int = 10) -> list[dict[str, Any]]:
        return [r.model_dump() for r in engine.similar(post_id, k=k)]

    @app.get("/users/{user_id}/feed")
    def feed(user_id: str, k: int = 10, explain: bool = False) -> list[dict[str, Any]]:
        results = profiles.feed(user_id, k=k, explain=explain)
        return [
            {**r.model_dump(), "why": r.reason}
            for r in results
        ]

    @app.get("/users/{user_id}/pair")
    def pair(user_id: str) -> list[dict[str, Any]]:
        return [r.model_dump() for r in profiles.pair(user_id)]

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

    class EventsRequest(BaseModel):
        events: list[EventIn] = Field(default_factory=list)

    @app.post("/users/{user_id}/events")
    def events(user_id: str, body: EventsRequest) -> dict[str, Any]:
        profile = None
        for ev in body.events:
            interaction = Interaction(user_id=user_id, **ev.model_dump())
            profile = profiles.record_event(interaction)
        return {
            "ok": True,
            "count": len(body.events),
            "persona_version": profile.persona_version if profile else None,
        }

    class TuneRequest(BaseModel):
        text: str

    @app.post("/users/{user_id}/tune")
    def tune(user_id: str, body: TuneRequest) -> dict[str, Any]:
        interaction = Interaction(
            user_id=user_id, event=EventType.TUNE, text=body.text
        )
        profile = profiles.record_event(interaction)
        return {"persona": profile.persona.model_dump(), "version": profile.persona_version}

    @app.get("/users/{user_id}/profile")
    def get_profile(user_id: str) -> dict[str, Any]:
        profile = profiles.get_or_create(user_id)
        data = profile.model_dump()
        # Don't dump huge vectors in list form for brevity in API responses optionally
        return data

    class OnboardRequest(BaseModel):
        free_text: str | None = None
        seed_post_ids: list[str] = Field(default_factory=list)

    @app.post("/users/{user_id}/onboard")
    def onboard(user_id: str, body: OnboardRequest) -> dict[str, Any]:
        try:
            profile = profiles.onboard(
                user_id, free_text=body.free_text, seed_post_ids=body.seed_post_ids
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return profile.persona.model_dump()

    @app.post("/users/{user_id}/persona/refresh")
    def refresh_persona(user_id: str) -> dict[str, Any]:
        profile = profiles.refresh_persona(user_id)
        return {
            "persona": profile.persona.model_dump(),
            "version": profile.persona_version,
        }

    return app


app = create_app()
