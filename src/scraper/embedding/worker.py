# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Embed pending Mongo posts into Qdrant."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from scraper.adapters import get_adapter
from scraper.config import Settings, get_settings
from scraper.embedding.chunker import chunk_content
from scraper.embedding.facets import extract_facets, facets_to_text
from scraper.llm.base import LLMClient
from scraper.llm.factory import get_indexing_client
from scraper.models.embeddable import SkipReason
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore
from scraper.tags.vocabulary import TagResolver, tag_refs_for_facets

logger = logging.getLogger(__name__)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    arr = np.asarray(vectors, dtype=np.float32)
    mean = arr.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm > 1e-12:
        mean = mean / norm
    return mean.tolist()


def _tag_resolver(
    store: MongoDocumentStore, client: LLMClient, settings: Settings
) -> TagResolver | None:
    """Resolver over the stored vocabulary, or None until ``scraper tags build`` has run."""
    tags = store.list_tags()
    if not tags:
        return None
    return TagResolver(
        tags,
        embed_fn=client.embed_query,
        threshold=settings.tag_cluster_threshold,
        theme_threshold=settings.theme_resolve_threshold,
    )


def _embed_one_raw(
    raw: dict[str, Any],
    *,
    store: MongoDocumentStore,
    vectors: QdrantVectorStore,
    client: LLMClient,
    settings: Settings,
    tag_resolver: TagResolver | None = None,
) -> str:
    """Embed a single Mongo document. Returns ``ready`` | ``skipped`` | ``failed``."""
    src = str(raw.get("source") or "unknown")
    external_id = str(raw.get("external_id") or "")
    try:
        adapter = get_adapter(src)
        adapted = adapter.adapt(raw)
        if isinstance(adapted, SkipReason):
            store.mark_embedding_skipped(src, external_id, adapted.value)
            logger.info("Skipped %s/%s: %s", src, external_id, adapted.value)
            return "skipped"

        chunks = chunk_content(adapted, settings)
        if not chunks:
            store.mark_embedding_skipped(src, external_id, SkipReason.NO_BODY.value)
            return "skipped"

        chunk_vectors: list[list[float]] = []
        for chunk in chunks:
            title = adapted.title if chunk.kind == "head" else None
            chunk_vectors.append(client.embed_document(chunk.text, title=title))

        doc_vector = _mean_vector(chunk_vectors)

        facets = None
        facet_vector = None
        if settings.facets_enabled:
            facets = extract_facets(adapted, client)
            facet_text = facets_to_text(facets)
            if facet_text:
                facet_vector = client.embed_document(facet_text, title=adapted.title)

        image_vector = None
        if settings.embed_images and adapted.image_urls:
            image_vector = client.embed_image(adapted.image_urls[0])

        payload = adapted.payload()
        canonical_tags: list[dict[str, Any]] | None = None
        if facets is not None:
            payload["topics"] = facets.topics
            payload["style"] = facets.style
            payload["emotion_primary"] = facets.emotion.primary()
            payload["reading_level"] = facets.reading_level
            if tag_resolver is not None:
                canonical_tags = [
                    ref.model_dump(mode="json")
                    for ref in tag_refs_for_facets(facets.model_dump(), tag_resolver)
                ]
                payload["tag_ids"] = [ref["id"] for ref in canonical_tags]

        point_id = vectors.upsert_post(
            source=src,
            external_id=external_id,
            chunk_vectors=chunk_vectors,
            doc_vector=doc_vector,
            facet_vector=facet_vector,
            image_vector=image_vector,
            payload=payload,
        )
        embed_model = (
            settings.litellm_embedding_model
            if settings.litellm_api_key
            else settings.gemini_embedding_model
        )
        store.mark_embedded(
            src,
            external_id,
            embedding_id=point_id,
            embedding_model=embed_model,
            content_hash=adapted.content_hash,
            chunk_count=len(chunks),
            facets=facets.model_dump() if facets else None,
            canonical_tags=canonical_tags,
        )
        logger.info("Embedded %s/%s (%d chunks)", src, external_id, len(chunks))
        return "ready"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to embed %s/%s", src, external_id)
        store.mark_embedding_failed(src, external_id, str(exc))
        return "failed"


def run_embed(
    *,
    limit: int | None = None,
    source: str | None = None,
    retry_failed: bool = False,
    force: bool = False,
    store: MongoDocumentStore | None = None,
    vectors: QdrantVectorStore | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    owns_store = store is None
    store = store or MongoDocumentStore(settings)
    owns_vectors = vectors is None
    vectors = vectors or QdrantVectorStore(settings)

    summary = {
        "ready": 0,
        "skipped": 0,
        "failed": 0,
        "processed": 0,
    }

    try:
        if not store.ping():
            raise RuntimeError("Cannot reach MongoDB. Run `make mongo-up`.")
        store.ensure_indexes()
        vectors.ensure_collection()
        gemini = client or get_indexing_client(settings)
        resolver = _tag_resolver(store, gemini, settings)

        for raw in store.iter_for_embedding(
            source=source,
            limit=limit,
            retry_failed=retry_failed,
            force=force,
        ):
            summary["processed"] += 1
            status = _embed_one_raw(
                raw,
                store=store,
                vectors=vectors,
                client=gemini,
                settings=settings,
                tag_resolver=resolver,
            )
            summary[status] += 1

        summary["stats"] = store.embedding_stats(source)
        return summary
    finally:
        if owns_store:
            store.close()
        if owns_vectors:
            vectors.close()


def embed_by_ids(
    post_ids: list[str],
    *,
    store: MongoDocumentStore | None = None,
    vectors: QdrantVectorStore | None = None,
    client: LLMClient | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Embed specific posts by Mongo ``_id`` (used after UGC create)."""
    settings = settings or get_settings()
    owns_store = store is None
    store = store or MongoDocumentStore(settings)
    owns_vectors = vectors is None
    vectors = vectors or QdrantVectorStore(settings)

    summary: dict[str, Any] = {
        "ready": 0,
        "skipped": 0,
        "failed": 0,
        "processed": 0,
        "missing": 0,
        "post_ids": list(post_ids),
    }

    try:
        if not store.ping():
            raise RuntimeError("Cannot reach MongoDB. Run `make mongo-up`.")
        store.ensure_indexes()
        vectors.ensure_collection()
        gemini = client or get_indexing_client(settings)
        resolver = _tag_resolver(store, gemini, settings)

        docs = store.get_many_by_ids(post_ids)
        for post_id in post_ids:
            raw = docs.get(post_id)
            if raw is None:
                summary["missing"] += 1
                continue
            summary["processed"] += 1
            status = _embed_one_raw(
                raw,
                store=store,
                vectors=vectors,
                client=gemini,
                settings=settings,
                tag_resolver=resolver,
            )
            summary[status] += 1

        return summary
    finally:
        if owns_store:
            store.close()
        if owns_vectors:
            vectors.close()
