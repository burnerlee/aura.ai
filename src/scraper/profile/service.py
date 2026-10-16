# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""UserProfileService: events, query-set building, feed, onboarding."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from scraper.config import Settings, get_settings
from scraper.llm.base import LLMClient
from scraper.llm.factory import (
    get_chat_client,
    get_indexing_client,
    get_inference_client,
)
from scraper.models.tag import TagKind
from scraper.models.user import (
    AuraConversationMessage,
    DNAPatch,
    DNARule,
    EventType,
    FeedbackReason,
    Interaction,
    InterestDNA,
    NoticedAttr,
    UserProfile,
)
from scraper.profile.aura import (
    MAX_STORED_MESSAGES,
    AuraChatMessage,
    AuraProfileDraft,
    AuraTurn,
    chat_with_aura,
    draft_to_persona,
    merge_conversation_context,
)
from scraper.profile.clusters import compute_centroids
from scraper.profile.dna import (
    CUSTOM_PREFIX,
    DNA_STEP,
    adjust_weight,
    apply_patch,
    build_dna_from_draft,
    confidence_scale,
    humanize,
    import_vector,
    reconcile,
    seed_dna,
)
from scraper.profile.patterns import (
    build_snapshot,
    merge_mined,
    mine_rules,
    noticed_for,
    observations_from_interactions,
)
from scraper.profile.persona import onboard_persona, synthesize_persona
from scraper.profile.state import update_state
from scraper.profile.weights import (
    apply_reason_actions,
    compute_read_ratio,
    compute_weight,
    is_explicit_negative,
)
from scraper.query.engine import RecommendationEngine
from scraper.query.types import (
    Filters,
    QueryKind,
    QuerySet,
    QueryVector,
    RuleSet,
    ScoredPost,
)
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore, point_id_for
from scraper.tags.service import TagService
from scraper.tags.vocabulary import TagResolver, slugify

logger = logging.getLogger(__name__)

# Explicit reactions that move the Interest DNA (not passive dwell / impressions).
_DNA_EVENTS = frozenset(
    {EventType.LIKE, EventType.SAVE, EventType.NOT_INTERESTED, EventType.PAIRWISE}
)
_MINING_WINDOW = 200  # most recent reactions considered when mining patterns
_DNA_QUERY_THEMES = 4  # top DNA themes that also act as retrieval queries
_DNA_QUERY_WEIGHT = 0.3  # their combined weight next to state / centroids / persona


@dataclass
class EventOutcome:
    """Result of recording one event: the profile plus what the UI can say about it."""

    profile: UserProfile
    # Attributes of a just-skipped post, offered as one-tap "what I noticed" chips.
    noticed: list[NoticedAttr] = field(default_factory=list)
    # Newly mined anti rules the user should confirm or dismiss.
    proposals: list[DNARule] = field(default_factory=list)


class UserProfileService:
    def __init__(
        self,
        *,
        store: MongoDocumentStore | None = None,
        vectors: QdrantVectorStore | None = None,
        engine: RecommendationEngine | None = None,
        client: LLMClient | None = None,
        inference_client: LLMClient | None = None,
        indexing_client: LLMClient | None = None,
        tag_service: TagService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or MongoDocumentStore(self.settings)
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self._indexing = indexing_client or client
        self._inference = inference_client or client
        self.engine = engine or RecommendationEngine(
            vectors=self.vectors,
            store=self.store,
            client=self._indexing,
            inference_client=self._inference,
            settings=self.settings,
        )
        self.tags = tag_service or TagService(
            store=self.store,
            vectors=self.vectors,
            client=self._indexing,
            settings=self.settings,
        )

    @property
    def client(self) -> LLMClient:
        """Indexing / embedding client (same vector space as the corpus)."""
        if self._indexing is None:
            self._indexing = get_indexing_client(self.settings)
        return self._indexing

    @property
    def inference(self) -> LLMClient:
        """User-side LLM (onboard / persona synthesis / rerank)."""
        if self._inference is None:
            self._inference = get_inference_client(self.settings)
        return self._inference

    def get_or_create(self, user_id: str) -> UserProfile:
        doc = self.store.users.find_one({"user_id": user_id})
        if doc:
            return UserProfile.from_mongo(doc)
        profile = UserProfile(user_id=user_id)
        self.save(profile)
        return profile

    def _resolver(self, *, embed: bool) -> TagResolver | None:
        """Tag resolver, or None if the vocabulary is unavailable (never blocks DNA)."""
        try:
            return self.tags.resolver(embed=embed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tag vocabulary unavailable (%s); using custom DNA keys", exc)
            return None

    def ensure_dna(self, profile: UserProfile) -> UserProfile:
        """Lazily migrate a pre-DNA profile, and heal keys after a tag rebuild."""
        if profile.dna.version == 0:
            seeded = seed_dna(profile, self._resolver(embed=True))
            if seeded is not None:
                profile.dna = seeded
                self.save(profile)
        elif profile.dna.weights:
            healed, changed = reconcile(profile.dna, self._resolver(embed=False))
            if changed:
                profile.dna = healed
                self.save(profile)
        return profile

    def get_dna(self, user_id: str) -> InterestDNA:
        return self.ensure_dna(self.get_or_create(user_id)).dna

    def patch_dna(self, user_id: str, patch: DNAPatch) -> InterestDNA:
        """Manual DNA edit. Raises ``DNAVersionConflict`` on a stale ``base_version``."""
        profile = self.ensure_dna(self.get_or_create(user_id))
        profile.dna = apply_patch(profile.dna, patch, resolver=self._resolver(embed=False))
        self.save(profile)
        return profile.dna

    def import_dna(
        self,
        user_id: str,
        *,
        vector: dict[str, float],
        prompt: str,
        excluded: list[str],
    ) -> tuple[InterestDNA, bool]:
        """Adopt the browser's local DNA once. Never overrides an existing server DNA."""
        profile = self.ensure_dna(self.get_or_create(user_id))
        if profile.dna.version > 0:
            return profile.dna, False
        imported = import_vector(
            vector,
            prompt=prompt,
            excluded=excluded,
            resolver=self._resolver(embed=True),
            previous=profile.dna,
        )
        if imported is None:
            return profile.dna, False
        profile.dna = imported
        self.save(profile)
        return profile.dna, True

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
        return self.record_event_outcome(interaction).profile

    def _post_theme(self, meta: dict[str, Any]) -> tuple[str, str] | None:
        """``(theme id, label)`` for a post: its tagged primary theme, else resolved."""
        for ref in meta.get("canonical_tags") or []:
            if isinstance(ref, dict) and ref.get("kind") == TagKind.THEME.value and ref.get("id"):
                return str(ref["id"]), str(ref.get("label") or ref["id"])
        facets = meta.get("facets") if isinstance(meta.get("facets"), dict) else {}
        user_meta = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
        labels = [
            user_meta.get("category"),
            *((facets or {}).get("topics") or []),
            *(meta.get("categories") or []),
        ]
        labels = [str(label).strip() for label in labels if label and str(label).strip()]
        resolver = self._resolver(embed=False)
        for label in labels:
            tag = resolver.resolve(label, TagKind.THEME) if resolver is not None else None
            if tag is not None:
                return tag.id, tag.label
        if labels and (slug := slugify(labels[0])):
            return f"{CUSTOM_PREFIX}{slug}", humanize(labels[0])
        return None

    def _learn_from_feedback(
        self,
        profile: UserProfile,
        interaction: Interaction,
        theme: tuple[str, str] | None,
    ) -> tuple[list[NoticedAttr], list[DNARule]]:
        """Move the DNA for this reaction, then re-mine post-level patterns."""
        self.ensure_dna(profile)
        weight = interaction.weight or 0.0
        if theme is not None:
            scale = confidence_scale(weight > 0, interaction.match_percent)
            profile.dna = adjust_weight(
                profile.dna, theme[0], theme[1], weight * DNA_STEP * scale
            )

        docs = (
            self.store.interactions.find(
                {"user_id": profile.user_id, "snapshot": {"$exists": True}}
            )
            .sort("ts", -1)
            .limit(_MINING_WINDOW)
        )
        observations = observations_from_interactions(docs)
        mined = mine_rules(observations, dismissed=profile.dna.dismissed)
        profile.dna, proposals = merge_mined(profile.dna, mined)
        noticed: list[NoticedAttr] = []
        if weight < 0 and interaction.snapshot:
            noticed = noticed_for(
                interaction.snapshot, observations, dismissed=profile.dna.dismissed
            )
        return noticed, proposals

    def record_event_outcome(self, interaction: Interaction) -> EventOutcome:
        profile = self.get_or_create(interaction.user_id)
        word_count = None
        meta: dict[str, Any] = {}
        theme: tuple[str, str] | None = None
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
        learns_dna = (
            bool(interaction.post_id) and bool(meta) and interaction.event in _DNA_EVENTS
        )
        if learns_dna:
            theme = self._post_theme(meta)
            interaction.snapshot = build_snapshot(
                meta,
                theme=theme,
                matched_label=interaction.matched_label,
                match_percent=interaction.match_percent,
            )
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

        noticed: list[NoticedAttr] = []
        proposals: list[DNARule] = []
        if learns_dna and weight != 0:
            noticed, proposals = self._learn_from_feedback(profile, interaction, theme)

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
        return EventOutcome(profile=profile, noticed=noticed, proposals=proposals)

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
            llm=self.inference,
            embed_client=self.client,
        )
        profile.persona = persona
        profile.persona_vector = vector
        profile.persona_version += 1
        profile.interaction_count_since_persona = 0
        self.save(profile)
        return profile

    def _stored_aura_messages(self, profile: UserProfile) -> list[AuraChatMessage]:
        return [
            AuraChatMessage(role=m.role, content=m.content)
            for m in profile.aura_conversation
            if m.content.strip()
        ]

    def _persist_aura_conversation(
        self,
        profile: UserProfile,
        session: list[AuraChatMessage],
        assistant_reply: str | None = None,
    ) -> UserProfile:
        """Merge session + latest assistant reply into hidden profile memory.

        Empty sessions (chat reopen / welcome-back) are not written — that would
        spam storage with greeting turns. Persistence starts once the user talks.
        """
        if not session:
            return profile
        stored = self._stored_aura_messages(profile)
        merged = merge_conversation_context(stored, session)
        if assistant_reply and assistant_reply.strip():
            reply = assistant_reply.strip()
            if not (
                merged
                and merged[-1].role == "assistant"
                and merged[-1].content == reply
            ):
                merged.append(AuraChatMessage(role="assistant", content=reply))
        profile.aura_conversation = [
            AuraConversationMessage(role=m.role, content=m.content)
            for m in merged[-MAX_STORED_MESSAGES:]
        ]
        self.save(profile)
        return profile

    def aura_chat(
        self,
        user_id: str,
        *,
        messages: list[AuraChatMessage],
        known_themes: list[str] | None = None,
        apply: bool = False,
        profile_draft: AuraProfileDraft | None = None,
    ) -> tuple[AuraTurn, UserProfile | None]:
        """One conversational turn with Aura; optionally persist a ready profile."""
        profile = self.get_or_create(user_id)
        prior = self._stored_aura_messages(profile)
        if not known_themes:
            known_themes = self._vocabulary_themes()

        if apply and profile_draft is not None:
            turn = AuraTurn(
                message="You're all set — I tuned your feed around this profile.",
                options=[],
                suggested_themes=list(profile_draft.themes[:4]),
                ready=True,
                profile=profile_draft,
            )
            profile = self.apply_aura_profile(user_id, profile_draft)
            profile = self._persist_aura_conversation(
                profile, messages, turn.message
            )
            return turn, profile

        llm: LLMClient | None
        fallback_llm: LLMClient | None = None
        try:
            llm = get_chat_client(self.settings)
        except RuntimeError:
            llm = None
        # Secondary: free-tier Gemini when LiteLLM is unavailable or errors.
        try:
            inference = self.inference
            if inference is not llm:
                fallback_llm = inference
        except RuntimeError:
            fallback_llm = None
        turn = chat_with_aura(
            messages,
            known_themes=known_themes,
            llm=llm,
            fallback_llm=fallback_llm,
            prior_messages=prior,
        )
        profile = self._persist_aura_conversation(profile, messages, turn.message)
        if apply and turn.ready and turn.profile is not None:
            profile = self.apply_aura_profile(user_id, turn.profile)
        return turn, profile

    def _vocabulary_themes(self) -> list[str]:
        try:
            return self.tags.top_labels()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load tag vocabulary for Aura (%s)", exc)
            return []

    def apply_aura_profile(
        self,
        user_id: str,
        draft: AuraProfileDraft,
    ) -> UserProfile:
        """Persist Aura's drafted profile as persona + embedding + Interest DNA."""
        profile = self.get_or_create(user_id)
        persona = draft_to_persona(draft)
        # Merge mutes from any prior persona.
        persona.muted_authors = list(profile.persona.muted_authors)
        persona.muted_sources = list(profile.persona.muted_sources)
        try:
            vector = self.client.embed_query(
                persona.summary or "; ".join(persona.topics) or "curious reader"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Aura profile embed failed (%s); empty vector", exc)
            vector = []
        profile.persona = persona
        profile.persona_vector = vector
        profile.persona_version += 1
        profile.interaction_count_since_persona = 0
        profile.dna = build_dna_from_draft(
            draft, self._resolver(embed=True), previous=profile.dna
        )
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
            free_text=free_text,
            seed_titles=titles,
            llm=self.inference,
            embed_client=self.client,
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
        vectors.extend(self._dna_query_vectors(profile))
        # Cold start: embed persona summary topics as content query
        if not vectors and profile.persona.summary:
            vec = self.client.embed_query(profile.persona.summary)
            vectors.append(
                QueryVector(vector=vec, weight=1.0, kind=QueryKind.PERSONA, label="persona")
            )
        return QuerySet(vectors=vectors)

    def _dna_query_vectors(self, profile: UserProfile) -> list[QueryVector]:
        """The user's top Interest DNA themes as retrieval queries.

        This is what makes the DNA the user sees the DNA that ranks: each top theme
        contributes its centroid, weighted by its share. Custom themes (no corpus
        theme yet) have no vector and are skipped.
        """
        if not profile.dna.weights:
            return []
        resolver = self._resolver(embed=False)
        if resolver is None:
            return []
        top = sorted(profile.dna.weights.items(), key=lambda kv: -kv[1])[:_DNA_QUERY_THEMES]
        total = sum(weight for _, weight in top) or 1.0
        out: list[QueryVector] = []
        for key, weight in top:
            tag = resolver.by_id(key)
            if tag is None or not tag.embedding:
                continue
            out.append(
                QueryVector(
                    vector=tag.embedding,
                    weight=_DNA_QUERY_WEIGHT * weight / total,
                    kind=QueryKind.THEME,
                    label=tag.label,
                )
            )
        return out

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
        profile = self.ensure_dna(self.get_or_create(user_id))
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
            rules=RuleSet(anti=profile.dna.anti, affinities=profile.dna.affinities),
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
