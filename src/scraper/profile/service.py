# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""UserProfileService: events, query-set building, feed, onboarding."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from scraper.config import Settings, get_settings
from scraper.llm.gemini import GeminiClient
from scraper.models.user import (
    EventType,
    FeedbackReason,
    Interaction,
    UserProfile,
)
from scraper.profile.clusters import compute_centroids
from scraper.profile.persona import onboard_persona, synthesize_persona
from scraper.profile.state import update_state
from scraper.profile.weights import (
    apply_reason_actions,
    compute_read_ratio,
    compute_weight,
    is_explicit_negative,
)
from scraper.query.engine import RecommendationEngine
from scraper.query.types import Filters, QueryKind, QuerySet, QueryVector, ScoredPost
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore, point_id_for

logger = logging.getLogger(__name__)


class UserProfileService:
    def __init__(
        self,
        *,
        store: MongoDocumentStore | None = None,
        vectors: QdrantVectorStore | None = None,
        engine: RecommendationEngine | None = None,
        client: GeminiClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or MongoDocumentStore(self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self.engine = engine or RecommendationEngine(
            vectors=self.vectors, store=self.store, client=client, settings=self.settings
        )
        self._client = client

    @property
    def client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(self.settings)
        return self._client

    def get_or_create(self, user_id: str) -> UserProfile:
        doc = self.store.users.find_one({"user_id": user_id})
        if doc:
            return UserProfile.from_mongo(doc)
        profile = UserProfile(user_id=user_id)
        self.save(profile)
        return profile

    def save(self, profile: UserProfile) -> None:
        profile.updated_at = datetime.now(UTC)
        self.store.users.update_one(
            {"user_id": profile.user_id},
            {"$set": profile.to_mongo()},
            upsert=True,
        )

    def _doc_vector(self, post_id: str) -> list[float] | None:
        raw = self.store.get_by_id(post_id)
        if not raw:
            records = self.vectors.fetch([post_id], with_vectors=["doc"])
        else:
            pid = point_id_for(str(raw["source"]), str(raw["external_id"]))
            records = self.vectors.fetch([pid], with_vectors=["doc"])
        if not records:
            return None
        vec = records[0].vector
        if isinstance(vec, dict):
            doc = vec.get("doc")
            return list(doc) if doc is not None else None
        return None

    def _post_meta(self, post_id: str) -> dict[str, Any]:
        raw = self.store.get_by_id(post_id) or {}
        return raw

    def record_event(self, interaction: Interaction) -> UserProfile:
        profile = self.get_or_create(interaction.user_id)
        word_count = None
        if interaction.post_id:
            meta = self._post_meta(interaction.post_id)
            word_count = meta.get("word_count")
            if interaction.event == EventType.DWELL and interaction.read_ratio is None:
                interaction.read_ratio = compute_read_ratio(
                    interaction.dwell_ms, word_count
                )

        weight = compute_weight(
            interaction,
            version=self.settings.weight_version,
            word_count=word_count,
        )
        # Pairwise loser convention: negative weight when text == "loser"
        if interaction.event == EventType.PAIRWISE and interaction.text == "loser":
            weight = -0.3
        interaction.weight = weight
        interaction.weight_version = self.settings.weight_version
        self.store.interactions.insert_one(interaction.to_mongo())

        if interaction.post_id:
            if interaction.post_id not in profile.seen_ids:
                profile.seen_ids.append(interaction.post_id)

        # Mute actions
        if interaction.event == EventType.MUTE_AUTHOR:
            author = interaction.text
            if not author and interaction.post_id:
                author = (self._post_meta(interaction.post_id).get("author") or {}).get(
                    "name"
                )
            if author and author not in profile.persona.muted_authors:
                profile.persona.muted_authors.append(author)
        if interaction.event == EventType.MUTE_SOURCE:
            source = interaction.text
            if not source and interaction.post_id:
                source = self._post_meta(interaction.post_id).get("source")
            if source and source not in profile.persona.muted_sources:
                profile.persona.muted_sources.append(source)

        profile.persona = apply_reason_actions(profile.persona, interaction)

        if interaction.reason == FeedbackReason.ALREADY_KNOW and interaction.post_id:
            if interaction.post_id not in profile.exclude_near_ids:
                profile.exclude_near_ids.append(interaction.post_id)

        # Positive / negative sets
        if interaction.post_id and weight > 0.2:
            if interaction.post_id not in profile.positive_ids:
                profile.positive_ids.append(interaction.post_id)
            vec = self._doc_vector(interaction.post_id)
            if vec is not None:
                positives = []
                for pid in profile.positive_ids[-50:]:
                    v = self._doc_vector(pid)
                    if v:
                        positives.append(v)
                profile.state_vector = update_state(
                    positives, liked=True, new_item=vec
                )
                profile.interest_centroids = compute_centroids(
                    positives, k=self.settings.interest_centroid_k
                )

        if interaction.post_id and is_explicit_negative(interaction):
            if interaction.post_id not in profile.negative_ids:
                profile.negative_ids.append(interaction.post_id)

        # Persona refresh triggers
        refresh = False
        if interaction.event == EventType.TUNE:
            refresh = True
        elif weight != 0:
            profile.interaction_count_since_persona += 1
            if (
                profile.interaction_count_since_persona
                >= self.settings.persona_refresh_every
            ):
                refresh = True

        self.save(profile)
        if refresh:
            profile = self.refresh_persona(profile.user_id)
        return profile

    def refresh_persona(self, user_id: str) -> UserProfile:
        profile = self.get_or_create(user_id)
        liked: list[str] = []
        for pid in profile.positive_ids[-20:]:
            meta = self._post_meta(pid)
            title = meta.get("title") or pid
            facets = meta.get("facets") or {}
            liked.append(f"{title} | facets={facets}")
        disliked: list[str] = []
        for pid in profile.negative_ids[-20:]:
            meta = self._post_meta(pid)
            disliked.append(meta.get("title") or pid)

        cursor = self.store.interactions.find({"user_id": user_id}).sort("ts", -1).limit(50)
        notes: list[str] = []
        tunes: list[str] = []
        for doc in cursor:
            if doc.get("reason"):
                notes.append(f"{doc.get('event')}:{doc.get('reason')} {doc.get('text') or ''}")
            if doc.get("event") == EventType.TUNE.value and doc.get("text"):
                tunes.append(doc["text"])
            if doc.get("event") == EventType.EXPLANATION_FEEDBACK.value and doc.get("text"):
                notes.append(f"explanation_feedback: {doc['text']}")

        persona, vector = synthesize_persona(
            profile,
            liked_summaries=liked,
            disliked_summaries=disliked,
            notes=notes,
            tunes=tunes,
            client=self.client,
        )
        profile.persona = persona
        profile.persona_vector = vector
        profile.persona_version += 1
        profile.interaction_count_since_persona = 0
        self.save(profile)
        return profile

    def onboard(
        self,
        user_id: str,
        *,
        free_text: str | None = None,
        seed_post_ids: list[str] | None = None,
    ) -> UserProfile:
        profile = self.get_or_create(user_id)
        titles: list[str] = []
        for pid in seed_post_ids or []:
            meta = self._post_meta(pid)
            titles.append(meta.get("title") or pid)
            if pid not in profile.positive_ids:
                profile.positive_ids.append(pid)
        persona, vector = onboard_persona(
            free_text=free_text, seed_titles=titles, client=self.client
        )
        profile.persona = persona
        profile.persona_vector = vector
        profile.persona_version += 1
        self.save(profile)
        return profile

    def build_query_set(self, profile: UserProfile) -> QuerySet:
        vectors: list[QueryVector] = []
        if profile.state_vector:
            vectors.append(
                QueryVector(
                    vector=profile.state_vector,
                    weight=0.35,
                    kind=QueryKind.STATE,
                    label="state",
                )
            )
        centroids = profile.interest_centroids
        if centroids:
            for c in centroids:
                vectors.append(
                    QueryVector(
                        vector=c.vector,
                        weight=0.4 * c.weight,
                        kind=QueryKind.CENTROID,
                        label=c.label or "centroid",
                    )
                )
        if profile.persona_vector:
            vectors.append(
                QueryVector(
                    vector=profile.persona_vector,
                    weight=0.25,
                    kind=QueryKind.PERSONA,
                    label="persona",
                )
            )
        # Cold start: embed persona summary topics as content query
        if not vectors and profile.persona.summary:
            vec = self.client.embed_query(profile.persona.summary)
            vectors.append(
                QueryVector(vector=vec, weight=1.0, kind=QueryKind.PERSONA, label="persona")
            )
        return QuerySet(vectors=vectors)

    def negative_set(self, profile: UserProfile) -> list[list[float]]:
        out: list[list[float]] = []
        for pid in profile.negative_ids[-30:]:
            vec = self._doc_vector(pid)
            if vec:
                out.append(vec)
        return out

    def feed(
        self,
        user_id: str,
        *,
        k: int = 10,
        explain: bool = False,
    ) -> list[ScoredPost]:
        profile = self.get_or_create(user_id)
        query_set = self.build_query_set(profile)
        if not query_set.vectors:
            return []
        exclude = list(
            dict.fromkeys(
                profile.seen_ids + profile.exclude_near_ids + profile.negative_ids
            )
        )
        # Convert mongo ids to point ids where possible
        exclude_points: list[str] = []
        for pid in exclude:
            raw = self.store.get_by_id(pid)
            if raw:
                exclude_points.append(
                    point_id_for(str(raw["source"]), str(raw["external_id"]))
                )
            else:
                exclude_points.append(pid)

        filters = Filters(
            muted_authors=profile.persona.muted_authors or None,
            muted_sources=profile.persona.muted_sources or None,
            max_words=profile.persona.max_words,
        )
        return self.engine.recommend(
            query_set,
            filters=filters,
            k=k,
            exclude_ids=exclude_points,
            negative_set=self.negative_set(profile),
            explain=explain,
            persona_text=profile.persona.summary,
        )

    def pair(self, user_id: str) -> list[ScoredPost]:
        """Two candidates from different interest centroids for pairwise cards."""
        profile = self.get_or_create(user_id)
        if len(profile.interest_centroids) < 2:
            return self.feed(user_id, k=2)[:2]
        results: list[ScoredPost] = []
        for centroid in profile.interest_centroids[:2]:
            qs = QuerySet(
                vectors=[
                    QueryVector(
                        vector=centroid.vector,
                        weight=1.0,
                        kind=QueryKind.CENTROID,
                        label=centroid.label,
                    )
                ]
            )
            picked = self.engine.recommend(qs, k=1, exclude_ids=profile.seen_ids)
            results.extend(picked)
        return results[:2]
