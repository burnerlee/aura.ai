# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Two-stage recommendation engine: ANN filter + set-to-set MaxSim rerank."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

import numpy as np

from scraper.config import Settings, get_settings
from scraper.llm.gemini import GeminiClient
from scraper.query.scoring import mmr, negative_penalty, recency_decay, set_similarity
from scraper.query.types import Filters, QueryKind, QuerySet, QueryVector, ScoredPost
from scraper.storage.mongodb import MongoDocumentStore
from scraper.storage.qdrant import QdrantVectorStore, point_id_for

logger = logging.getLogger(__name__)


class RecommendationEngine:
    def __init__(
        self,
        *,
        vectors: QdrantVectorStore | None = None,
        store: MongoDocumentStore | None = None,
        client: GeminiClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vectors = vectors or QdrantVectorStore(self.settings)
        self.store = store or MongoDocumentStore(self.settings)
        self._client = client

    @property
    def client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(self.settings)
        return self._client

    def _candidate_filter(
        self,
        query_set: QuerySet,
        filters: Filters | None,
        exclude_ids: list[str] | None,
        filter_k: int,
    ) -> dict[str, int]:
        hits: dict[str, int] = defaultdict(int)
        filt = filters.to_dict() if filters else None
        for qv in query_set.vectors:
            vector_name = "facet" if qv.kind == QueryKind.FACET else "doc"
            try:
                results = self.vectors.search(
                    vector_name,
                    qv.vector,
                    k=filter_k,
                    filt=filt,
                    exclude_ids=exclude_ids,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("ANN search failed on %s: %s", vector_name, exc)
                if vector_name != "doc":
                    results = self.vectors.search(
                        "doc",
                        qv.vector,
                        k=filter_k,
                        filt=filt,
                        exclude_ids=exclude_ids,
                    )
                else:
                    raise
            for point in results:
                hits[str(point.id)] += 1
        return dict(hits)

    def recommend(
        self,
        query_set: QuerySet,
        *,
        filters: Filters | None = None,
        k: int = 10,
        exclude_ids: list[str] | None = None,
        negative_set: list[list[float]] | None = None,
        explain: bool = False,
        persona_text: str | None = None,
    ) -> list[ScoredPost]:
        if not query_set.vectors:
            return []

        filter_k = self.settings.filter_k
        candidates = self._candidate_filter(query_set, filters, exclude_ids, filter_k)
        if not candidates:
            return []

        # Prefer candidates hit by more query vectors
        ordered_ids = sorted(candidates.keys(), key=lambda i: -candidates[i])
        records = self.vectors.fetch(ordered_ids, with_vectors=["chunks", "doc"])
        record_map = {str(r.id): r for r in records}

        q_vecs = [qv.vector for qv in query_set.vectors]
        q_weights = [qv.weight for qv in query_set.vectors]
        q_labels = [
            qv.label or qv.kind.value for qv in query_set.vectors
        ]

        now = time.time()
        scores: dict[str, float] = {}
        per_query: dict[str, dict[str, float]] = {}
        doc_centroids: dict[str, list[float]] = {}
        payloads: dict[str, dict[str, Any]] = {}
        reasons: dict[str, str] = {}

        for pid, record in record_map.items():
            vecs = record.vector or {}
            chunks = vecs.get("chunks") if isinstance(vecs, dict) else None
            doc = vecs.get("doc") if isinstance(vecs, dict) else None
            if not chunks:
                continue
            if isinstance(chunks[0], (int, float)):
                chunks = [chunks]
            base = set_similarity(q_vecs, chunks, weights=q_weights, sigma="max")
            penalty = negative_penalty(
                chunks,
                negative_set or [],
                scale=self.settings.negative_penalty_scale,
            )
            payload = dict(record.payload or {})
            if filters and filters.max_words and payload.get("word_count"):
                if int(payload["word_count"]) > filters.max_words:
                    continue
            decay = recency_decay(
                payload.get("published_at"),
                now_epoch=now,
                half_life_days=self.settings.recency_half_life_days,
            )
            final = (base - penalty) * decay

            # Per-query attribution for "why"
            attr: dict[str, float] = {}
            for qv, label in zip(query_set.vectors, q_labels, strict=True):
                attr[label] = set_similarity(
                    [qv.vector], chunks, weights=[1.0], sigma="max"
                )
            top_label = max(attr, key=attr.get) if attr else "content"
            reasons[pid] = f"matched your {top_label} interest"

            scores[pid] = final
            per_query[pid] = attr
            if doc is not None:
                doc_centroids[pid] = list(doc)
            else:
                doc_centroids[pid] = list(np.mean(chunks, axis=0))
            payloads[pid] = payload

        # Author diversity: keep at most N per author before MMR
        by_author: dict[str, list[str]] = defaultdict(list)
        for pid in sorted(scores, key=lambda i: -scores[i]):
            author = (payloads[pid].get("author_name") or "unknown").lower()
            if len(by_author[author]) < self.settings.author_diversity_cap:
                by_author[author].append(pid)
        diverse_ids = [pid for ids in by_author.values() for pid in ids]
        diverse_ids.sort(key=lambda i: -scores[i])

        selected = mmr(
            diverse_ids,
            scores,
            doc_centroids,
            k=k,
            lambda_=self.settings.mmr_lambda,
        )

        results = [
            ScoredPost(
                post_id=str(payloads[pid].get("post_id") or pid),
                point_id=pid,
                score=scores[pid],
                payload=payloads[pid],
                per_query_scores=per_query[pid],
                reason=reasons[pid],
            )
            for pid in selected
        ]

        if explain and results:
            results = self._llm_rerank(results, persona_text=persona_text)
        return results

    def _llm_rerank(
        self,
        results: list[ScoredPost],
        *,
        persona_text: str | None,
        top_n: int = 10,
    ) -> list[ScoredPost]:
        head = results[:top_n]
        titles = [
            f"{i+1}. {r.payload.get('title') or r.post_id}" for i, r in enumerate(head)
        ]
        prompt = (
            "Rerank these articles for the user. Return a JSON object with key "
            "'items' as a list of {index: int (1-based), why: str} in preferred order.\n"
            f"Persona: {persona_text or 'general reader'}\n"
            "Articles:\n" + "\n".join(titles)
        )
        try:
            from pydantic import BaseModel, Field

            class Item(BaseModel):
                index: int
                why: str

            class Rerank(BaseModel):
                items: list[Item] = Field(default_factory=list)

            rerank = self.client.generate_json(prompt, Rerank)
            reordered: list[ScoredPost] = []
            seen: set[int] = set()
            for item in rerank.items:
                idx = item.index - 1
                if 0 <= idx < len(head) and idx not in seen:
                    post = head[idx].model_copy(update={"reason": item.why})
                    reordered.append(post)
                    seen.add(idx)
            for i, post in enumerate(head):
                if i not in seen:
                    reordered.append(post)
            return reordered + results[top_n:]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM rerank failed: %s", exc)
            return results

    def search(
        self,
        text: str,
        *,
        k: int = 10,
        filters: Filters | None = None,
        explain: bool = False,
    ) -> list[ScoredPost]:
        vector = self.client.embed_query(text)
        query_set = QuerySet(
            vectors=[QueryVector(vector=vector, weight=1.0, kind=QueryKind.CONTENT, label="query")]
        )
        return self.recommend(query_set, filters=filters, k=k, explain=explain)

    def similar(
        self,
        post_id: str,
        *,
        k: int = 10,
        filters: Filters | None = None,
    ) -> list[ScoredPost]:
        # Resolve Mongo id -> point id
        raw = self.store.get_by_id(post_id)
        if raw:
            pid = point_id_for(str(raw["source"]), str(raw["external_id"]))
        else:
            pid = post_id
        records = self.vectors.fetch([pid], with_vectors=["chunks"])
        if not records:
            return []
        chunks = records[0].vector.get("chunks") if isinstance(records[0].vector, dict) else None
        if not chunks:
            return []
        if isinstance(chunks[0], (int, float)):
            chunks = [chunks]
        weight = 1.0 / len(chunks)
        query_set = QuerySet(
            vectors=[
                QueryVector(
                    vector=list(c),
                    weight=weight,
                    kind=QueryKind.CONTENT,
                    label="seed",
                )
                for c in chunks
            ]
        )
        return self.recommend(
            query_set,
            filters=filters,
            k=k,
            exclude_ids=[pid],
        )
