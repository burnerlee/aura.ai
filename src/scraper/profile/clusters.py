# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Interest centroids via lightweight k-means over positive doc vectors."""

from __future__ import annotations

import numpy as np

from scraper.models.user import InterestCentroid


def _normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-12, None)
    return mat / norms


def compute_centroids(
    vectors: list[list[float]],
    *,
    weights: list[float] | None = None,
    k: int = 6,
    max_iter: int = 25,
    seed: int = 42,
) -> list[InterestCentroid]:
    if not vectors:
        return []
    x = np.asarray(vectors, dtype=np.float32)
    n, dim = x.shape
    k = min(k, n)
    w = np.ones(n, dtype=np.float32) if weights is None else np.asarray(weights, dtype=np.float32)
    w = np.clip(w, 1e-6, None)

    rng = np.random.default_rng(seed)
    # k-means++ style init
    centers = np.empty((k, dim), dtype=np.float32)
    centers[0] = x[rng.integers(0, n)]
    for i in range(1, k):
        dists = np.min(
            np.sum((x[:, None, :] - centers[None, :i, :]) ** 2, axis=2),
            axis=1,
        )
        probs = dists * w
        probs = probs / np.clip(probs.sum(), 1e-12, None)
        centers[i] = x[rng.choice(n, p=probs)]

    labels = np.zeros(n, dtype=np.int32)
    for _ in range(max_iter):
        dists = np.sum((x[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(dists, axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            mask = labels == i
            if not mask.any():
                centers[i] = x[rng.integers(0, n)]
                continue
            centers[i] = np.average(x[mask], axis=0, weights=w[mask])

    centers = _normalize_rows(centers)
    centroids: list[InterestCentroid] = []
    for i in range(k):
        mask = labels == i
        mass = float(w[mask].sum()) if mask.any() else 0.0
        if mass <= 0:
            continue
        centroids.append(
            InterestCentroid(vector=centers[i].tolist(), weight=mass, label=f"interest_{i}")
        )
    total = sum(c.weight for c in centroids) or 1.0
    return [
        InterestCentroid(vector=c.vector, weight=c.weight / total, label=c.label)
        for c in centroids
    ]
