# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Set-to-set similarity scoring (DESSERT-style F = A ∘ σ)."""

from __future__ import annotations

from typing import Literal

import numpy as np

Sigma = Literal["max", "softmax_mean", "top_k_mean"]


def _as_matrix(vectors: list[list[float]] | np.ndarray) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr


def pairwise_cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity matrix shape (|a|, |b|). Assumes roughly unit vectors."""
    a_norm = a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-12, None)
    b_norm = b / np.clip(np.linalg.norm(b, axis=1, keepdims=True), 1e-12, None)
    return a_norm @ b_norm.T


def _sigma(sims: np.ndarray, sigma: Sigma, top_k: int = 3) -> float:
    if sims.size == 0:
        return 0.0
    if sigma == "max":
        return float(np.max(sims))
    if sigma == "softmax_mean":
        # Softmax over similarities then expectation
        shifted = sims - np.max(sims)
        weights = np.exp(shifted)
        weights = weights / np.clip(weights.sum(), 1e-12, None)
        return float(np.dot(weights, sims))
    if sigma == "top_k_mean":
        k = min(top_k, sims.size)
        top = np.partition(sims, -k)[-k:]
        return float(top.mean())
    raise ValueError(f"Unknown sigma: {sigma}")


def set_similarity(
    query_vectors: list[list[float]] | np.ndarray,
    doc_vectors: list[list[float]] | np.ndarray,
    weights: list[float] | np.ndarray | None = None,
    sigma: Sigma = "max",
    top_k: int = 3,
) -> float:
    """F(Q, S) = A({σ(sim(q, S)) : q ∈ Q}) with A = weighted mean."""
    q = _as_matrix(query_vectors)
    s = _as_matrix(doc_vectors)
    if q.size == 0 or s.size == 0:
        return 0.0
    sims = pairwise_cosine(q, s)  # (|Q|, |S|)
    per_q = np.array([_sigma(sims[i], sigma, top_k) for i in range(q.shape[0])])
    if weights is None:
        w = np.ones(q.shape[0], dtype=np.float32)
    else:
        w = np.asarray(weights, dtype=np.float32)
        if w.shape[0] != q.shape[0]:
            raise ValueError("weights length must match query vectors")
    w_sum = float(w.sum())
    if w_sum <= 0:
        return 0.0
    return float(np.dot(w, per_q) / w_sum)


def negative_penalty(
    doc_vectors: list[list[float]] | np.ndarray,
    negative_vectors: list[list[float]] | np.ndarray,
    scale: float = 0.35,
) -> float:
    """Penalty = scale * max cosine between doc centroid and negatives."""
    if not len(negative_vectors):
        return 0.0
    s = _as_matrix(doc_vectors)
    n = _as_matrix(negative_vectors)
    if s.size == 0 or n.size == 0:
        return 0.0
    doc_centroid = s.mean(axis=0, keepdims=True)
    sims = pairwise_cosine(doc_centroid, n)[0]
    return float(scale * np.max(sims))


def recency_decay(
    published_at_epoch: float | None,
    *,
    now_epoch: float,
    half_life_days: float = 30.0,
) -> float:
    """Multiplicative recency factor in (0, 1]. Missing date -> 1.0."""
    if published_at_epoch is None:
        return 1.0
    age_days = max(0.0, (now_epoch - published_at_epoch) / 86400.0)
    return float(0.5 ** (age_days / max(half_life_days, 1e-6)))


def mmr(
    candidate_ids: list[str],
    scores: dict[str, float],
    vectors: dict[str, list[float]],
    *,
    k: int,
    lambda_: float = 0.7,
) -> list[str]:
    """Maximal Marginal Relevance over candidate ids."""
    if not candidate_ids:
        return []
    selected: list[str] = []
    remaining = list(candidate_ids)
    while remaining and len(selected) < k:
        best_id = None
        best_score = -1e18
        for cid in remaining:
            relevance = scores.get(cid, 0.0)
            if not selected:
                diversity = 0.0
            else:
                cvec = np.asarray(vectors[cid], dtype=np.float32).reshape(1, -1)
                svecs = np.asarray(
                    [vectors[sid] for sid in selected], dtype=np.float32
                )
                diversity = float(np.max(pairwise_cosine(cvec, svecs)))
            mmr_score = lambda_ * relevance - (1.0 - lambda_) * diversity
            if mmr_score > best_score:
                best_score = mmr_score
                best_id = cid
        assert best_id is not None
        selected.append(best_id)
        remaining.remove(best_id)
    return selected
