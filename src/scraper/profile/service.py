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
    label_for_key,
    reconcile,
    seed_dna,
)
from scraper.profile.insight import UserPost, build_insight, unit
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
# Stated interests: the persona summary, the topics the user named, and the DNA themes.
_PERSONA_QUERY_WEIGHT = 0.35
_TOPIC_QUERY_COUNT = 4
_TOPIC_QUERY_WEIGHT = 0.4
_DNA_QUERY_THEMES = 4  # top DNA themes that also act as retrieval queries
_DNA_QUERY_WEIGHT = 0.25
# Each like shifts this much of the query weight from stated interests to behaviour.
_BEHAVIOUR_SHARE_PER_LIKE = 0.08
_MAX_BEHAVIOUR_SHARE = 0.6
_INSIGHT_LIKED = 30  # most recent liked / skipped posts a "why this" can point back to
_INSIGHT_SKIPPED = 20


def _scaled(vectors: list[QueryVector], share: float) -> list[QueryVector]:
    """Rescale a group's weights so they sum to ``share``."""
    total = sum(v.weight for v in vectors)
    if share <= 0 or total <= 0:
        return []
    return [v.model_copy(update={"weight": v.weight / total * share}) for v in vectors]


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
        self._theme_vectors: dict[str, list[float]] = {}

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

        # Toggle semantics for explicit feedback:
        # - Clicking "resonate" twice should undo it (same for banish).
        #
        # The UI currently always emits LIKE / NOT_INTERESTED, so the server is the
        # source of truth for whether that reaction is being applied or removed.
        toggled_off = False
        if interaction.post_id and learns_dna:
            if interaction.event == EventType.LIKE and interaction.post_id in profile.positive_ids:
                # Undo a previous like: remove it from the positive set and apply the
                # inverse theme delta. Record the interaction as neutral (weight=0)
                # so it does not count as a positive/negative signal for mining.
                self.ensure_dna(profile)
                theme = self._post_theme(meta)
                if theme is not None:
                    scale = confidence_scale(True, interaction.match_percent)
                    profile.dna = adjust_weight(
                        profile.dna, theme[0], theme[1], -(weight * DNA_STEP * scale)
                    )
                profile.positive_ids = [
                    pid
                    for pid in profile.positive_ids
                    if pid != interaction.post_id
                ]
                # Recompute state/centroids from the remaining positives (cheap window).
                positives: list[list[float]] = []
                for pid in profile.positive_ids[-50:]:
                    vec = self._doc_vector(pid)
                    if vec:
                        positives.append(vec)
                profile.state_vector = update_state(positives, liked=False)
                profile.interest_centroids = (
                    compute_centroids(positives, k=self.settings.interest_centroid_k)
                    if positives
                    else []
                )
                weight = 0.0
                interaction.weight = 0.0
                toggled_off = True
            elif (
                interaction.event == EventType.NOT_INTERESTED
                and interaction.post_id in profile.negative_ids
            ):
                # Undo a previous banish: remove it from the negative set and apply
                # the inverse theme delta; store as neutral for mining.
                self.ensure_dna(profile)
                theme = self._post_theme(meta)
                if theme is not None:
                    scale = confidence_scale(False, interaction.match_percent)
                    profile.dna = adjust_weight(
                        profile.dna, theme[0], theme[1], -(weight * DNA_STEP * scale)
                    )
                profile.negative_ids = [
                    pid
                    for pid in profile.negative_ids
                    if pid != interaction.post_id
                ]
                weight = 0.0
                interaction.weight = 0.0
                toggled_off = True

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

        # Undo toggles should not mutate persona fields via reason chips.
        if not toggled_off:
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

        # Negative_ids should only reflect active negative feedback (not an undo toggle).
        if interaction.post_id and weight < 0 and is_explicit_negative(interaction):
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

    def reset(self, user_id: str) -> UserProfile:
        """Forget everything learned about the user; the account link itself survives."""
        self.store.interactions.delete_many({"user_id": user_id})
        profile = UserProfile(user_id=user_id)
        self.store.users.replace_one({"user_id": user_id}, profile.to_mongo(), upsert=True)
        return profile

    def rebuild_vectors(self, user_id: str) -> UserProfile:
        """Recompute every user-side vector from the current corpus embedding model."""
        profile = self.get_or_create(user_id)
        summary = profile.persona.summary or "; ".join(profile.persona.topics)
        profile.persona_vector = self.client.embed_query(summary) if summary else None
        positives = [v for pid in profile.positive_ids[-50:] if (v := self._doc_vector(pid))]
        profile.state_vector = update_state(positives, liked=False)
        profile.interest_centroids = (
            compute_centroids(positives, k=self.settings.interest_centroid_k)
            if positives
            else []
        )
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
            current_profile=self._describe_profile(profile),
        )
        profile = self._persist_aura_conversation(profile, messages, turn.message)
        # A ready turn always retunes the feed, so a chat edit takes effect without
        # an extra "apply" step.
        if turn.ready and turn.profile is not None:
            profile = self.apply_aura_profile(user_id, turn.profile)
        return turn, profile

    def _describe_profile(self, profile: UserProfile) -> str | None:
        """Plain-text summary of the current persona + DNA for Aura's prompt."""
        persona = profile.persona
        dna = profile.dna
        if not (persona.summary or dna.weights):
            return None
        themes = ", ".join(
            f"{label_for_key(key, dna.labels, None)} {weight:.0f}%"
            for key, weight in sorted(dna.weights.items(), key=lambda kv: -kv[1])[:8]
        )
        avoid = ", ".join(r.label or r.key for r in dna.anti[:8])
        lines = [
            f"summary: {persona.summary}" if persona.summary else "",
            f"themes: {themes}" if themes else "",
            f"avoiding: {avoid}" if avoid else "",
        ]
        return "\n".join(line for line in lines if line)

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
            logger.warning("Aura profile embed failed (%s); keeping previous vector", exc)
            vector = profile.persona_vector
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
        """Blend what the user told Aura with what they reacted to.

        Stated interests (persona + DNA themes) lead until enough likes exist to
        trust behaviour; one like must never drown out a whole conversation.
        """
        behaviour: list[QueryVector] = []
        if profile.state_vector:
            behaviour.append(
                QueryVector(
                    vector=profile.state_vector,
                    weight=0.45,
                    kind=QueryKind.STATE,
                    label="state",
                )
            )
        for c in profile.interest_centroids:
            behaviour.append(
                QueryVector(
                    vector=c.vector,
                    weight=0.55 * c.weight,
                    kind=QueryKind.CENTROID,
                    label=c.label or "centroid",
                )
            )

        stated: list[QueryVector] = []
        persona_vector = profile.persona_vector
        if not persona_vector and profile.persona.summary:
            persona_vector = self.client.embed_query(profile.persona.summary)
        if persona_vector:
            stated.append(
                QueryVector(
                    vector=persona_vector,
                    weight=_PERSONA_QUERY_WEIGHT,
                    kind=QueryKind.PERSONA,
                    label="persona",
                )
            )
        stated.extend(self._topic_query_vectors(profile))
        stated.extend(self._dna_query_vectors(profile))

        likes = len(profile.positive_ids)
        behaviour_share = min(_MAX_BEHAVIOUR_SHARE, _BEHAVIOUR_SHARE_PER_LIKE * likes)
        if not stated:
            behaviour_share = 1.0
        elif not behaviour:
            behaviour_share = 0.0
        return QuerySet(
            vectors=[
                *_scaled(behaviour, behaviour_share),
                *_scaled(stated, 1.0 - behaviour_share),
            ]
        )

    def _theme_vector(self, label: str) -> list[float] | None:
        """Embedding for a DNA theme the corpus vocabulary does not know yet."""
        key = label.strip().lower()
        if not key:
            return None
        if key not in self._theme_vectors:
            try:
                self._theme_vectors[key] = self.client.embed_query(label)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not embed DNA theme %r (%s)", label, exc)
                return None
        return self._theme_vectors[key]

    def _topic_query_vectors(self, profile: UserProfile) -> list[QueryVector]:
        """The specific topics the user named to Aura, as retrieval queries.

        DNA themes are coarse corpus buckets ("neuroscience" lands in Health & Wellness);
        the user's own words keep retrieval as specific as they were.
        """
        topics = [t for t in profile.persona.topics if t.strip()][:_TOPIC_QUERY_COUNT]
        ranked = [(t, 1.0 - 0.15 * i) for i, t in enumerate(topics)]
        total = sum(w for _, w in ranked) or 1.0
        out: list[QueryVector] = []
        for topic, weight in ranked:
            vector = self._theme_vector(topic)
            if vector:
                out.append(
                    QueryVector(
                        vector=vector,
                        weight=_TOPIC_QUERY_WEIGHT * weight / total,
                        kind=QueryKind.THEME,
                        label=topic,
                    )
                )
        return out

    def _dna_query_vectors(self, profile: UserProfile) -> list[QueryVector]:
        """The user's top Interest DNA themes as retrieval queries.

        This is what makes the DNA the user sees the DNA that ranks: each top theme
        contributes its centroid (or, for a custom theme, its label's embedding),
        weighted by its share.
        """
        if not profile.dna.weights:
            return []
        resolver = self._resolver(embed=False)
        top = sorted(profile.dna.weights.items(), key=lambda kv: -kv[1])[:_DNA_QUERY_THEMES]
        total = sum(weight for _, weight in top) or 1.0
        out: list[QueryVector] = []
        for key, weight in top:
            tag = resolver.by_id(key) if resolver is not None else None
            if tag is not None:
                label = tag.label
                vector = tag.embedding or self._theme_vector(label)
            else:
                label = label_for_key(key, profile.dna.labels, None)
                vector = self._theme_vector(label)
            if not vector:
                continue
            out.append(
                QueryVector(
                    vector=vector,
                    weight=_DNA_QUERY_WEIGHT * weight / total,
                    kind=QueryKind.THEME,
                    label=label,
                )
            )
        return out

    def _reacted_posts(self, post_ids: list[str]) -> list[UserPost]:
        """Posts the user reacted to, with titles, topic tags and doc embeddings.

        Two batched lookups (Mongo, then Qdrant) no matter how many posts.
        """
        docs = self.store.get_many_by_ids(post_ids)
        points = {
            point_id_for(str(doc["source"]), str(doc["external_id"])): pid
            for pid, doc in docs.items()
            if doc.get("source") and doc.get("external_id")
        }
        if not points:
            return []
        out: list[UserPost] = []
        for record in self.vectors.fetch(list(points), with_vectors=["doc"]):
            vector = record.vector.get("doc") if isinstance(record.vector, dict) else None
            doc = docs.get(points.get(str(record.id), ""))
            if vector is None or doc is None:
                continue
            title = (doc.get("title") or "").strip() or str(doc.get("summary") or "").strip()
            if not title:
                continue
            out.append(
                UserPost(
                    post_id=str(doc["_id"]),
                    title=title,
                    vector=unit(vector),
                    topic_ids=frozenset(
                        t for t in doc.get("tag_ids") or [] if str(t).startswith("topic:")
                    ),
                )
            )
        return out

    def _attach_insights(self, profile: UserProfile, results: list[ScoredPost]) -> None:
        """Give every result a plain-language, evidence-based reason it is in the feed."""
        if not results:
            return
        liked = self._reacted_posts(profile.positive_ids[-_INSIGHT_LIKED:])
        skipped = self._reacted_posts(profile.negative_ids[-_INSIGHT_SKIPPED:])
        resolver = self._resolver(embed=False)

        def label(tag_id: str) -> str:
            tag = resolver.by_id(tag_id) if resolver is not None else None
            return tag.label if tag is not None else humanize(tag_id)

        for result in results:
            result.insight = build_insight(
                result, dna=profile.dna, liked=liked, skipped=skipped, label=label
            )

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
        results = self.engine.recommend(
            query_set,
            filters=filters,
            k=k,
            exclude_ids=exclude_points,
            negative_set=self.negative_set(profile),
            rules=RuleSet(anti=profile.dna.anti, affinities=profile.dna.affinities),
            explain=explain,
            persona_text=profile.persona.summary,
        )
        self._attach_insights(profile, results)
        return results

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

    def merge_profiles(self, *, from_user_id: str, to_user_id: str) -> UserProfile:
        """Merge one user's state into another, recomputing derived vectors.

        Used when an anonymous session signs in and becomes an account.
        """
        if not from_user_id or not to_user_id or from_user_id == to_user_id:
            return self.get_or_create(to_user_id or from_user_id or "anonymous")

        src = self.get_or_create(from_user_id)
        dst = self.get_or_create(to_user_id)

        def _dedupe(items: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for item in items:
                if not item:
                    continue
                if item in seen:
                    continue
                seen.add(item)
                out.append(item)
            return out

        # Merge raw id lists (preserve dst ordering, append src extras).
        dst.seen_ids = _dedupe(dst.seen_ids + src.seen_ids)
        dst.exclude_near_ids = _dedupe(dst.exclude_near_ids + src.exclude_near_ids)
        dst.positive_ids = _dedupe(dst.positive_ids + src.positive_ids)
        dst.negative_ids = _dedupe(dst.negative_ids + src.negative_ids)

        # Merge persona hints / controls.
        dst.persona.muted_authors = _dedupe(
            list(dst.persona.muted_authors) + list(src.persona.muted_authors)
        )
        dst.persona.muted_sources = _dedupe(
            list(dst.persona.muted_sources) + list(src.persona.muted_sources)
        )
        if not (dst.persona.summary or "").strip() and (src.persona.summary or "").strip():
            dst.persona = src.persona
            dst.persona_vector = src.persona_vector
        elif dst.persona_vector is None and src.persona_vector is not None:
            dst.persona_vector = src.persona_vector

        # Merge Aura memory (keep bounded).
        if src.aura_conversation:
            merged = list(dst.aura_conversation) + list(src.aura_conversation)
            dst.aura_conversation = merged[-MAX_STORED_MESSAGES:]

        # Merge Interest DNA (server-owned weights + rules).
        if getattr(dst, "dna", None) is not None and getattr(src, "dna", None) is not None:
            if dst.dna.version <= 0 and src.dna.version > 0:
                dst.dna = src.dna
            else:
                # Weights/labels: keep dst as authoritative, but fill in anything missing from src.
                for key, value in (src.dna.weights or {}).items():
                    if key not in dst.dna.weights:
                        dst.dna.weights[key] = value
                for key, value in (src.dna.labels or {}).items():
                    if key not in dst.dna.labels:
                        dst.dna.labels[key] = value
                if not (dst.dna.prompt or "").strip() and (src.dna.prompt or "").strip():
                    dst.dna.prompt = src.dna.prompt

                def _rule_key(rule: Any) -> str:
                    kind = getattr(rule, "kind", "") or ""
                    rkey = getattr(rule, "key", "") or ""
                    return f"{kind}:{rkey}"

                existing_anti = {_rule_key(r): r for r in dst.dna.anti}
                for r in src.dna.anti:
                    existing_anti.setdefault(_rule_key(r), r)
                dst.dna.anti = list(existing_anti.values())

                existing_aff = {_rule_key(r): r for r in dst.dna.affinities}
                for r in src.dna.affinities:
                    existing_aff.setdefault(_rule_key(r), r)
                dst.dna.affinities = list(existing_aff.values())

                dst.dna.dismissed = _dedupe(list(dst.dna.dismissed) + list(src.dna.dismissed))
                dst.dna.version = max(dst.dna.version, src.dna.version) + 1
                dst.dna.updated_at = datetime.now(UTC)

        # Recompute derived vectors from the merged positive set.
        positives: list[list[float]] = []
        for pid in dst.positive_ids[-50:]:
            vec = self._doc_vector(pid)
            if vec:
                positives.append(vec)
        if positives:
            dst.state_vector = update_state(positives, liked=False, new_item=None)
            dst.interest_centroids = compute_centroids(
                positives, k=self.settings.interest_centroid_k
            )

        # Best-effort: migrate interactions history so persona refresh keeps context.
        try:
            self.store.interactions.update_many(
                {"user_id": from_user_id},
                {"$set": {"user_id": to_user_id}},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Interaction migration failed (%s -> %s): %s",
                from_user_id,
                to_user_id,
                exc,
            )

        # Advance persona version to signal a state change.
        dst.persona_version = max(dst.persona_version, src.persona_version) + 1
        dst.interaction_count_since_persona = 0
        self.save(dst)
        return dst
