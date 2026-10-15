# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""RecommendationEngine with a fake vector store."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from scraper.query.engine import RecommendationEngine
from scraper.query.types import QueryKind, QuerySet, QueryVector


class FakeVectors:
    def __init__(self, points: dict[str, dict]):
        self.points = points

    def search(self, vector_name, vector, *, k=10, filt=None, exclude_ids=None):
        exclude = set(exclude_ids or [])
        scored = []
        q = np.asarray(vector, dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        for pid, data in self.points.items():
            if pid in exclude:
                continue
            doc = np.asarray(data["doc"], dtype=np.float32)
            doc = doc / max(float(np.linalg.norm(doc)), 1e-12)
            score = float(np.dot(q, doc))
            scored.append(SimpleNamespace(id=pid, score=score, payload=data["payload"]))
        scored.sort(key=lambda p: -p.score)
        return scored[:k]

    def fetch(self, ids, *, with_vectors=False):
        out = []
        for pid in ids:
            if pid not in self.points:
                continue
            data = self.points[pid]
            out.append(
                SimpleNamespace(
                    id=pid,
                    payload=data["payload"],
                    vector={"chunks": data["chunks"], "doc": data["doc"]},
                )
            )
        return out


def test_candidate_union_and_rerank_order():
    points = {
        "a": {
            "doc": [1.0, 0.0],
            "chunks": [[1.0, 0.0], [0.9, 0.1]],
            "payload": {"post_id": "a", "title": "A", "author_name": "x", "published_at": None},
        },
        "b": {
            "doc": [0.0, 1.0],
            "chunks": [[0.0, 1.0]],
            "payload": {"post_id": "b", "title": "B", "author_name": "y", "published_at": None},
        },
        "c": {
            "doc": [0.7, 0.7],
            "chunks": [[0.7, 0.7]],
            "payload": {"post_id": "c", "title": "C", "author_name": "z", "published_at": None},
        },
    }
    engine = RecommendationEngine(vectors=FakeVectors(points))  # type: ignore[arg-type]
    engine.settings.filter_k = 10
    engine.settings.author_diversity_cap = 5
    engine.settings.mmr_lambda = 1.0  # pure relevance

    qs = QuerySet(
        vectors=[
            QueryVector(vector=[1.0, 0.0], weight=1.0, kind=QueryKind.CONTENT, label="q")
        ]
    )
    results = engine.recommend(qs, k=2)
    assert results[0].post_id == "a"
    assert len(results) == 2
