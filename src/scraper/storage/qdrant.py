# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Qdrant vector store with named vectors for multi-vector posts."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient, models

from scraper.config import Settings, get_settings

logger = logging.getLogger(__name__)

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def point_id_for(source: str, external_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{source}:{external_id}"))


class QdrantVectorStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            check_compatibility=False,
        )

    @property
    def collection(self) -> str:
        return self.settings.qdrant_collection

    def ensure_collection(self) -> None:
        dim = self.settings.embedding_dim
        name = self.collection
        existing = {c.name for c in self._client.get_collections().collections}
        if name in existing:
            return

        vectors_config: dict[str, models.VectorParams] = {
            "chunks": models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
                multivector_config=models.MultiVectorConfig(
                    comparator=models.MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=models.HnswConfigDiff(m=0),
            ),
            "doc": models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
            ),
            "facet": models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
            ),
            "image": models.VectorParams(
                size=dim,
                distance=models.Distance.COSINE,
            ),
        }
        self._client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
        )
        for field, schema in (
            ("source", models.PayloadSchemaType.KEYWORD),
            ("categories", models.PayloadSchemaType.KEYWORD),
            ("tags", models.PayloadSchemaType.KEYWORD),
            ("author_name", models.PayloadSchemaType.KEYWORD),
            ("language", models.PayloadSchemaType.KEYWORD),
            ("published_at", models.PayloadSchemaType.FLOAT),
            ("post_id", models.PayloadSchemaType.KEYWORD),
            ("topics", models.PayloadSchemaType.KEYWORD),
            ("style", models.PayloadSchemaType.KEYWORD),
            ("emotion_primary", models.PayloadSchemaType.KEYWORD),
        ):
            self._client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=schema,
            )
        logger.info("Created Qdrant collection %s", name)

    def upsert_post(
        self,
        *,
        source: str,
        external_id: str,
        chunk_vectors: list[list[float]],
        doc_vector: list[float],
        facet_vector: list[float] | None = None,
        image_vector: list[float] | None = None,
        payload: dict[str, Any],
    ) -> str:
        self.ensure_collection()
        pid = point_id_for(source, external_id)
        vectors: dict[str, Any] = {
            "chunks": chunk_vectors,
            "doc": doc_vector,
        }
        if facet_vector is not None:
            vectors["facet"] = facet_vector
        if image_vector is not None:
            vectors["image"] = image_vector

        self._client.upsert(
            collection_name=self.collection,
            points=[
                models.PointStruct(
                    id=pid,
                    vector=vectors,
                    payload=payload,
                )
            ],
        )
        return pid

    def _build_filter(
        self,
        filt: dict[str, Any] | None,
        exclude_ids: list[str] | None = None,
    ) -> models.Filter | None:
        must: list[models.FieldCondition] = []
        must_not: list[models.FieldCondition | models.HasIdCondition] = []
        if filt:
            if sources := filt.get("sources"):
                must.append(
                    models.FieldCondition(
                        key="source",
                        match=models.MatchAny(any=list(sources)),
                    )
                )
            if categories := filt.get("categories"):
                must.append(
                    models.FieldCondition(
                        key="categories",
                        match=models.MatchAny(any=list(categories)),
                    )
                )
            if tags := filt.get("tags"):
                must.append(
                    models.FieldCondition(
                        key="tags",
                        match=models.MatchAny(any=list(tags)),
                    )
                )
            if authors := filt.get("authors"):
                must.append(
                    models.FieldCondition(
                        key="author_name",
                        match=models.MatchAny(any=list(authors)),
                    )
                )
            if language := filt.get("language"):
                must.append(
                    models.FieldCondition(
                        key="language",
                        match=models.MatchValue(value=language),
                    )
                )
            if published_after := filt.get("published_after"):
                must.append(
                    models.FieldCondition(
                        key="published_at",
                        range=models.Range(gte=float(published_after)),
                    )
                )
            if muted_authors := filt.get("muted_authors"):
                must_not.append(
                    models.FieldCondition(
                        key="author_name",
                        match=models.MatchAny(any=list(muted_authors)),
                    )
                )
            if muted_sources := filt.get("muted_sources"):
                must_not.append(
                    models.FieldCondition(
                        key="source",
                        match=models.MatchAny(any=list(muted_sources)),
                    )
                )
            if max_words := filt.get("max_words"):
                must.append(
                    models.FieldCondition(
                        key="word_count",
                        range=models.Range(lte=int(max_words)),
                    )
                )
        if exclude_ids:
            must_not.append(models.HasIdCondition(has_id=list(exclude_ids)))
        if not must and not must_not:
            return None
        return models.Filter(must=must or None, must_not=must_not or None)

    def search(
        self,
        vector_name: str,
        vector: list[float] | list[list[float]],
        *,
        k: int = 10,
        filt: dict[str, Any] | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[models.ScoredPoint]:
        self.ensure_collection()
        return list(
            self._client.query_points(
                collection_name=self.collection,
                query=vector,
                using=vector_name,
                query_filter=self._build_filter(filt, exclude_ids),
                limit=k,
                with_payload=True,
                with_vectors=False,
            ).points
        )

    def fetch(
        self,
        ids: list[str],
        *,
        with_vectors: bool | list[str] = False,
    ) -> list[models.Record]:
        if not ids:
            return []
        self.ensure_collection()
        records = self._client.retrieve(
            collection_name=self.collection,
            ids=ids,
            with_payload=True,
            with_vectors=with_vectors,
        )
        return list(records)

    def delete(self, source: str, external_id: str) -> None:
        pid = point_id_for(source, external_id)
        self._client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=[pid]),
        )

    def close(self) -> None:
        self._client.close()
