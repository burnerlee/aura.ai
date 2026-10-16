# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""FastAPI app: search, similar, feed, events, profile, onboard, persona, posts."""

from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper.api.cards import FeedCard, mongo_to_card
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
    AuraChatRequest,
    DNAImportRequest,
    EventsRequest,
    OnboardRequest,
    SearchRequest,
    TuneRequest,
)
from scraper.embedding.worker import embed_by_ids
from scraper.models.tag import TagKind
from scraper.models.user import DNAPatch, EventType, Interaction
from scraper.profile.aura import AuraChatMessage, AuraProfileDraft
from scraper.profile.dna import DNAVersionConflict
from scraper.profile.service import UserProfileService
from scraper.query.engine import RecommendationEngine
from scraper.query.types import Filters
from scraper.tags.service import TagService


def create_app(
    *,
    engine: RecommendationEngine | None = None,
    profiles: UserProfileService | None = None,
    tags: TagService | None = None,
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
    tag_service = tags or TagService(store=store, vectors=engine.vectors)

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

    @app.get("/discover")
    def discover(
        k: int = 40,
        source: str | None = None,
        ready_only: bool = True,
    ) -> list[FeedCard]:
        """Popularity / recency browse (Discover tab) — not personalized ranking."""
        docs = store.list_discover(limit=k, source=source, ready_only=ready_only)
        return [mongo_to_card(doc) for doc in docs]

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
        outcome = None
        for ev in body.events:
            interaction = Interaction(user_id=user_id, **ev.model_dump())
            outcome = profiles.record_event_outcome(interaction)
        profile = outcome.profile if outcome else None
        return {
            "ok": True,
            "count": len(body.events),
            "persona_version": profile.persona_version if profile else None,
            # The DNA after learning from these events, so the UI can update in place.
            "dna": profile.dna.model_dump(mode="json") if profile else None,
            # From the last event: attributes of a skipped post to offer as chips, and
            # newly mined avoidances awaiting the user's confirm / dismiss.
            "noticed": [n.model_dump(mode="json") for n in outcome.noticed] if outcome else [],
            "proposals": (
                [r.model_dump(mode="json") for r in outcome.proposals] if outcome else []
            ),
        }

    @app.post("/users/{user_id}/tune")
    def tune(user_id: str, body: TuneRequest) -> dict[str, Any]:
        interaction = Interaction(
            user_id=user_id, event=EventType.TUNE, text=body.text
        )
        profile = profiles.record_event(interaction)
        return {"persona": profile.persona.model_dump(), "version": profile.persona_version}

    @app.get("/tags")
    def list_tags(
        kind: TagKind | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        min_docs: int = Query(default=1, ge=0),
    ) -> list[dict[str, Any]]:
        """Canonical tag vocabulary (topics / styles), most common first."""
        return tag_service.list_public(kind=kind, limit=limit, min_docs=min_docs)

    @app.get("/users/{user_id}/dna")
    def get_dna(user_id: str) -> dict[str, Any]:
        return profiles.get_dna(user_id).model_dump(mode="json")

    @app.patch("/users/{user_id}/dna")
    def patch_dna(user_id: str, body: DNAPatch) -> dict[str, Any]:
        try:
            dna = profiles.patch_dna(user_id, body)
        except DNAVersionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": str(exc), "current_version": exc.current_version},
            ) from exc
        return dna.model_dump(mode="json")

    @app.post("/users/{user_id}/dna/import")
    def import_dna(user_id: str, body: DNAImportRequest) -> dict[str, Any]:
        """One-time adoption of the browser's local DNA; a no-op if the server has one."""
        dna, imported = profiles.import_dna(
            user_id,
            vector=body.vector,
            prompt=body.prompt,
            excluded=body.excluded_categories,
        )
        return {"imported": imported, "dna": dna.model_dump(mode="json")}

    @app.get("/users/{user_id}/profile")
    def get_profile(user_id: str) -> dict[str, Any]:
        profile = profiles.ensure_dna(profiles.get_or_create(user_id))
        # Keep Aura chat memory server-side; UI never needs the transcript.
        data = profile.model_dump()
        data.pop("aura_conversation", None)
        data["conversation_turns"] = len(profile.aura_conversation)
        return data

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

    @app.post("/users/{user_id}/aura/chat")
    def aura_chat(user_id: str, body: AuraChatRequest) -> dict[str, Any]:
        """Conversational personalization with Aura."""
        messages = [
            AuraChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
            for m in body.messages
            if m.role in ("user", "assistant") and m.content.strip()
        ]
        draft = (
            AuraProfileDraft.model_validate(body.profile.model_dump())
            if body.profile is not None
            else None
        )
        try:
            turn, profile = profiles.aura_chat(
                user_id,
                messages=messages,
                known_themes=body.known_themes,
                apply=body.apply,
                profile_draft=draft,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        payload: dict[str, Any] = turn.model_dump()
        # Conversation text stays on the profile for Aura memory; not returned to UI.
        if profile is not None:
            if body.apply:
                payload["persona"] = profile.persona.model_dump()
                payload["persona_version"] = profile.persona_version
                payload["dna"] = profile.dna.model_dump(mode="json")
            payload["conversation_turns"] = len(profile.aura_conversation)
        return payload

    return app


app = create_app()
