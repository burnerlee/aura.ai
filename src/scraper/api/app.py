# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""FastAPI app: search, similar, feed, events, profile, onboard, persona, posts."""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper.api.cards import FeedCard
from scraper.api.posts import (
    CreatePostRequest,
    CreatePostResponse,
    create_user_post,
    get_card,
    get_cards,
    hydrate_results,
    maybe_embed_post,
)
from scraper.api.schemas import (
    EventsRequest,
    OnboardRequest,
    SearchRequest,
    TuneRequest,
)
from scraper.embedding.worker import embed_by_ids
from scraper.models.user import EventType, Interaction
from scraper.profile.service import UserProfileService
from scraper.query.engine import RecommendationEngine
from scraper.query.types import Filters


def create_app(
    *,
    engine: RecommendationEngine | None = None,
    profiles: UserProfileService | None = None,
) -> FastAPI:
    app = FastAPI(title="Content Recommendation API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = engine or RecommendationEngine()
    profiles = profiles or UserProfileService(engine=engine)
    store = engine.store

    @app.get("/health")
    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/search")
    def search(body: SearchRequest) -> list[FeedCard]:
        filters = Filters(sources=body.sources) if body.sources else None
        results = engine.search(
            body.query, k=body.k, filters=filters, explain=body.explain
        )
        return hydrate_results(store, results)

    @app.get("/posts/{post_id}/similar")
    def similar(post_id: str, k: int = 10) -> list[FeedCard]:
        return hydrate_results(store, engine.similar(post_id, k=k))

    @app.get("/posts/{post_id}", response_model=FeedCard)
    def get_post(post_id: str) -> FeedCard:
        card = get_card(store, post_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Post not found")
        return card

    @app.get("/posts", response_model=list[FeedCard])
    def list_posts(
        ids: list[str] = Query(default_factory=list),
    ) -> list[FeedCard]:
        if not ids:
            return []
        return get_cards(store, ids)

    @app.post("/posts", response_model=CreatePostResponse)
    def create_post(
        body: CreatePostRequest,
        background_tasks: BackgroundTasks,
    ) -> CreatePostResponse:
        try:
            raw, card = create_user_post(body, store=store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        post_id = str(raw["_id"])
        embedding_summary: dict[str, Any] | None = None
        if body.wait_for_embed:
            embedding_summary = maybe_embed_post(post_id, wait=True, store=store)
            refreshed = get_card(store, post_id)
            if refreshed is not None:
                card = refreshed
        else:
            background_tasks.add_task(embed_by_ids, [post_id], store=store)

        return CreatePostResponse(post=card, embedding_summary=embedding_summary)

    @app.post("/posts/{post_id}/embed")
    def embed_post(post_id: str) -> dict[str, Any]:
        if store.get_by_id(post_id) is None:
            raise HTTPException(status_code=404, detail="Post not found")
        return embed_by_ids([post_id], store=store)

    @app.get("/users/{user_id}/feed")
    def feed(user_id: str, k: int = 10, explain: bool = False) -> list[FeedCard]:
        results = profiles.feed(user_id, k=k, explain=explain)
        return hydrate_results(store, results)

    @app.get("/users/{user_id}/pair")
    def pair(user_id: str) -> list[FeedCard]:
        return hydrate_results(store, profiles.pair(user_id))

    @app.post("/users/{user_id}/events")
    def events(user_id: str, body: EventsRequest) -> dict[str, Any]:
        # UI mapping: resonate → like, banish → not_interested, bookmark → save.
        # ``post_id`` must be the Mongo ``_id`` string from FeedCard.id.
        profile = None
        for ev in body.events:
            interaction = Interaction(user_id=user_id, **ev.model_dump())
            profile = profiles.record_event(interaction)
        return {
            "ok": True,
            "count": len(body.events),
            "persona_version": profile.persona_version if profile else None,
        }

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
        return profile.model_dump()

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
