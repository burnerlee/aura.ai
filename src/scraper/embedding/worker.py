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
from scraper.llm.gemini import GeminiClient
from scraper.models.embeddable import SkipReason
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore

logger = logging.getLogger(__name__)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    arr = np.asarray(vectors, dtype=np.float32)
    mean = arr.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm > 1e-12:
        mean = mean / norm
    return mean.tolist()


def run_embed(
    *,
    limit: int | None = None,
    source: str | None = None,
    retry_failed: bool = False,
    force: bool = False,
    store: MongoDocumentStore | None = None,
    vectors: QdrantVectorStore | None = None,
    client: GeminiClient | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    owns_store = store is None
    store = store or MongoDocumentStore(settings)
    owns_vectors = vectors is None
    vectors = vectors or QdrantVectorStore(settings)
    owns_client = client is None

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
        gemini = client or GeminiClient(settings)

        for raw in store.iter_for_embedding(
            source=source,
            limit=limit,
            retry_failed=retry_failed,
            force=force,
        ):
            summary["processed"] += 1
            src = str(raw.get("source") or "unknown")
            external_id = str(raw.get("external_id") or "")
            try:
                adapter = get_adapter(src)
                adapted = adapter.adapt(raw)
                if isinstance(adapted, SkipReason):
                    store.mark_embedding_skipped(src, external_id, adapted.value)
                    summary["skipped"] += 1
                    logger.info("Skipped %s/%s: %s", src, external_id, adapted.value)
                    continue

                chunks = chunk_content(adapted, settings)
                if not chunks:
                    store.mark_embedding_skipped(src, external_id, SkipReason.NO_BODY.value)
                    summary["skipped"] += 1
                    continue

                chunk_vectors: list[list[float]] = []
                for chunk in chunks:
                    title = adapted.title if chunk.kind == "head" else None
                    chunk_vectors.append(
                        gemini.embed_document(chunk.text, title=title)
                    )

                doc_vector = _mean_vector(chunk_vectors)

                facets = None
                facet_vector = None
                if settings.facets_enabled:
                    facets = extract_facets(adapted, gemini)
                    facet_text = facets_to_text(facets)
                    if facet_text:
                        facet_vector = gemini.embed_document(
                            facet_text, title=adapted.title
                        )

                image_vector = None
                if settings.embed_images and adapted.image_urls:
                    image_vector = gemini.embed_image(adapted.image_urls[0])

                payload = adapted.payload()
                if facets is not None:
                    payload["topics"] = facets.topics
                    payload["style"] = facets.style
                    payload["emotion_primary"] = facets.emotion.primary()

                point_id = vectors.upsert_post(
                    source=src,
                    external_id=external_id,
                    chunk_vectors=chunk_vectors,
                    doc_vector=doc_vector,
                    facet_vector=facet_vector,
                    image_vector=image_vector,
                    payload=payload,
                )
                store.mark_embedded(
                    src,
                    external_id,
                    embedding_id=point_id,
                    embedding_model=settings.gemini_embedding_model,
                    content_hash=adapted.content_hash,
                    chunk_count=len(chunks),
                    facets=facets.model_dump() if facets else None,
                )
                summary["ready"] += 1
                logger.info(
                    "Embedded %s/%s (%d chunks)", src, external_id, len(chunks)
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to embed %s/%s", src, external_id)
                store.mark_embedding_failed(src, external_id, str(exc))
                summary["failed"] += 1

        summary["stats"] = store.embedding_stats(source)
        return summary
    finally:
        if owns_store:
            store.close()
        if owns_vectors:
            vectors.close()
        if owns_client:
            pass
