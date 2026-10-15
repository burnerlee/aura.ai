# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Self-attention user state update (Social Image Rec Eqs. 6–9, no RL)."""

from __future__ import annotations

import numpy as np


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm < 1e-12:
        return vec
    return vec / norm


def update_state(
    positive_vectors: list[list[float]],
    *,
    liked: bool,
    new_item: list[float] | None = None,
) -> list[float] | None:
    """Update the user state vector.

    If ``liked`` and ``new_item`` is provided:
        s = (x_i + sum_j softmax(x_i · x_j) x_j) / 2  over the positive set
        (including x_i).
    Else:
        s = mean(positive_vectors)
    """
    if not positive_vectors and new_item is None:
        return None

    positives = [np.asarray(v, dtype=np.float32) for v in positive_vectors]
    if new_item is not None and liked:
        xi = np.asarray(new_item, dtype=np.float32)
        # Ensure xi is in the set for attention
        pool = positives + [xi] if not any(np.allclose(p, xi) for p in positives) else positives
        if not pool:
            return _normalize(xi).tolist()
        dots = np.array([float(np.dot(xi, xj)) for xj in pool], dtype=np.float32)
        shifted = dots - dots.max()
        weights = np.exp(shifted)
        weights = weights / np.clip(weights.sum(), 1e-12, None)
        attended = sum(w * xj for w, xj in zip(weights, pool, strict=True))
        state = (xi + attended) / 2.0
        return _normalize(np.asarray(state, dtype=np.float32)).tolist()

    if not positives:
        return None
    mean = np.mean(np.stack(positives, axis=0), axis=0)
    return _normalize(mean).tolist()


def softmax_attention_weights(
    query: list[float],
    keys: list[list[float]],
) -> list[float]:
    """Expose softmax weights for tests (sum to 1)."""
    if not keys:
        return []
    q = np.asarray(query, dtype=np.float32)
    dots = np.array(
        [float(np.dot(q, np.asarray(k, dtype=np.float32))) for k in keys],
        dtype=np.float32,
    )
    shifted = dots - dots.max()
    weights = np.exp(shifted)
    weights = weights / np.clip(weights.sum(), 1e-12, None)
    return weights.tolist()
