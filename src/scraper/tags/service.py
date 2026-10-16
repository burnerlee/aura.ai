# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Build the canonical tag vocabulary from corpus facets and tag posts with it."""

from __future__ import annotations

import logging
import time
from typing import Any

from scraper.config import Settings, get_settings
from scraper.llm.base import LLMClient
from scraper.llm.factory import get_indexing_client
from scraper.models.tag import Tag, TagKind
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore
from scraper.tags.themes import build_themes, group_topics_with_llm, themes_from_groups
from scraper.tags.vocabulary import (
    LabelEntry,
    TagResolver,
    build_tags,
    collapse_labels,
    is_usable_label,
    normalize_label,
    tag_refs_for_facets,
)

logger = logging.getLogger(__name__)

# Which PostFacets field feeds which tag kind.
_FACET_FIELDS: tuple[tuple[TagKind, str], ...] = (
    (TagKind.TOPIC, "topics"),
    (TagKind.STYLE, "style"),
)
_BATCH = 200
# Hot paths (feed, events, DNA reads) build a resolver per request; the vocabulary only
# changes on rebuild, so a short cache avoids reloading every tag embedding each time.
_VOCAB_TTL_SECONDS = 30.0


class TagService:
    def __init__(
        self,
        *,
        store: MongoDocumentStore,
        vectors: QdrantVectorStore | None = None,
        client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store
        self.vectors = vectors
        self._client = client
        self._vocab: list[Tag] | None = None
        self._vocab_at = 0.0

    def vocabulary(self) -> list[Tag]:
        now = time.monotonic()
        if self._vocab is None or now - self._vocab_at > _VOCAB_TTL_SECONDS:
            self._vocab = self.store.list_tags()
            self._vocab_at = now
        return self._vocab

    def invalidate(self) -> None:
        self._vocab = None

    @property
    def client(self) -> LLMClient:
        """Embedding client (same vector space as the corpus)."""
        if self._client is None:
            self._client = get_indexing_client(self.settings)
        return self._client

    def _embed(self, text: str) -> list[float]:
        return self.client.embed_query(text)

    def resolver(self, *, embed: bool = True) -> TagResolver:
        """Resolver over the stored vocabulary; ``embed`` enables nearest-tag fallback."""
        return TagResolver(
            self.vocabulary(),
            embed_fn=self._embed if embed else None,
            threshold=self.settings.tag_cluster_threshold,
            theme_threshold=self.settings.theme_resolve_threshold,
        )

    def list_public(
        self,
        *,
        kind: TagKind | None = None,
        limit: int = 100,
        min_docs: int = 1,
    ) -> list[dict[str, Any]]:
        tags = self.store.list_tags(
            kind=kind, min_docs=min_docs, include_merged=False, limit=limit
        )
        return [t.to_public() for t in tags]

    def top_labels(self, *, limit: int = 16) -> list[str]:
        """Most common topic labels, for seeding Aura's ``known_themes``."""
        tags = self.store.list_tags(
            kind=TagKind.TOPIC, min_docs=1, include_merged=False, limit=limit
        )
        return [t.label for t in tags]

    def rebuild(
        self,
        *,
        threshold: float | None = None,
        dry_run: bool = False,
        apply: bool = True,
    ) -> dict[str, Any]:
        """Re-derive the vocabulary from every embedded post's facets."""
        cutoff = self.settings.tag_cluster_threshold if threshold is None else threshold
        existing = {t.id: t for t in self.store.list_tags()}
        known_vectors = {
            (t.kind, normalize_label(t.label)): t.embedding
            for t in existing.values()
            if t.embedding
        }

        summary: dict[str, Any] = {"threshold": cutoff, "embed_failed": 0, "kinds": {}}
        new_tags: list[Tag] = []
        for kind, field in _FACET_FIELDS:
            counts = {
                label: n
                for label, n in self.store.facet_label_counts(field).items()
                if is_usable_label(label)
            }
            entries: list[LabelEntry] = []
            for item in collapse_labels(counts):
                vector = known_vectors.get((kind, item.normalized))
                if not vector:
                    try:
                        vector = self._embed(item.label)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Embed failed for tag label %r: %s", item.label, exc)
                        summary["embed_failed"] += 1
                        continue
                entries.append(LabelEntry(label=item.label, count=item.count, vector=vector))
            preferred = {
                normalize_label(t.label)
                for t in existing.values()
                if t.kind == kind and t.merged_into is None
            }
            built = build_tags(kind, entries, threshold=cutoff, preferred=preferred)
            summary["kinds"][kind.value] = {
                "labels": len(entries),
                "tags": len(built),
                "merged": sum(1 for t in built if t.aliases),
            }
            new_tags.extend(built)

        topics = [t for t in new_tags if t.kind == TagKind.TOPIC]
        themes, parent_of = self._build_themes(topics, existing)
        for topic in topics:
            topic.parent_id = parent_of.get(topic.id)
        new_tags.extend(themes)
        summary["themes"] = {
            "count": len(themes),
            "method": "llm" if self._themes_via_llm else "embedding",
        }

        summary["tags"] = len(new_tags)
        if dry_run:
            summary["theme_labels"] = [
                {"label": th.label, "topics": sum(1 for p in parent_of.values() if p == th.id)}
                for th in sorted(themes, key=lambda th: -th.doc_count)
            ]
            summary["clusters"] = [
                {"id": t.id, "label": t.label, "aliases": t.aliases, "docs": t.doc_count}
                for t in sorted(new_tags, key=lambda t: -len(t.aliases))
                if t.aliases
            ][:50]
            return summary

        stale = self._retire(existing, new_tags)
        self.store.save_tags(new_tags + stale)
        self.invalidate()
        summary["retired"] = len(stale)
        if apply:
            summary["apply"] = self.apply()
        return summary

    _themes_via_llm = False

    def _build_themes(
        self, topics: list[Tag], existing: dict[str, Tag]
    ) -> tuple[list[Tag], dict[str, str]]:
        """Coarse themes over the topic tags: LLM grouping, embedding k-means fallback."""
        self._themes_via_llm = False
        preferred = [
            t.label
            for t in existing.values()
            if t.kind == TagKind.THEME and t.merged_into is None and t.doc_count > 0
        ]
        groups = group_topics_with_llm(topics, self.client, preferred)
        if groups:
            themes, parent_of = themes_from_groups(topics, groups)
            if themes:
                self._themes_via_llm = True
                return themes, parent_of
        logger.warning("Using embedding-only theme clustering (LLM grouping unavailable)")
        return build_themes(topics)

    @staticmethod
    def _retire(existing: dict[str, Tag], new_tags: list[Tag]) -> list[Tag]:
        """Zero out tags that left the vocabulary; link them to their replacement."""
        new_ids = {t.id for t in new_tags}
        alias_index: dict[tuple[TagKind, str], str] = {}
        for tag in new_tags:
            for form in (tag.label, *tag.aliases):
                alias_index[(tag.kind, normalize_label(form))] = tag.id
        stale: list[Tag] = []
        for old in existing.values():
            if old.id in new_ids:
                continue
            target = alias_index.get((old.kind, normalize_label(old.label)))
            old.doc_count = 0
            old.merged_into = target or old.merged_into
            stale.append(old)
        return stale

    def apply(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Resolve every embedded post's facets to tags; sync Mongo, Qdrant, doc counts."""
        resolver = self.resolver()
        summary = {"processed": 0, "tagged": 0, "untagged": 0, "qdrant_failed": 0}
        if self.vectors is not None:
            self.vectors.ensure_payload_index("tag_ids")

        batch: list[tuple[Any, list[dict[str, Any]]]] = []

        def flush() -> None:
            self.store.set_post_tags(batch)
            batch.clear()

        for raw in self.store.iter_for_tagging(source=source, limit=limit):
            summary["processed"] += 1
            refs = [
                r.model_dump(mode="json")
                for r in tag_refs_for_facets(raw.get("facets"), resolver)
            ]
            summary["tagged" if refs else "untagged"] += 1
            batch.append((raw["_id"], refs))
            if self.vectors is not None:
                try:
                    self.vectors.set_payload(
                        str(raw["source"]),
                        str(raw["external_id"]),
                        {"tag_ids": [r["id"] for r in refs]},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Qdrant tag payload failed for %s: %s", raw["_id"], exc)
                    summary["qdrant_failed"] += 1
            if len(batch) >= _BATCH:
                flush()
        flush()

        self.store.set_tag_doc_counts(self.store.tag_doc_counts())
        self.invalidate()
        return summary
