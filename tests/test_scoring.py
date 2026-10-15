# Copyright (c) 2026 DevRev Inc. All rights reserved.

import numpy as np

from scraper.query.scoring import mmr, negative_penalty, set_similarity


def test_maxsim_matches_bruteforce():
    q = [[1.0, 0.0], [0.0, 1.0]]
    s = [[0.9, 0.1], [0.1, 0.9], [0.5, 0.5]]
    score = set_similarity(q, s, sigma="max")
    # Manual MaxSim then mean
    qn = np.array(q)
    sn = np.array(s)
    qn = qn / np.linalg.norm(qn, axis=1, keepdims=True)
    sn = sn / np.linalg.norm(sn, axis=1, keepdims=True)
    sims = qn @ sn.T
    expected = float(sims.max(axis=1).mean())
    assert abs(score - expected) < 1e-5


def test_weights():
    q = [[1.0, 0.0], [0.0, 1.0]]
    s = [[1.0, 0.0]]
    equal = set_similarity(q, s, weights=[1, 1], sigma="max")
    skewed = set_similarity(q, s, weights=[1, 0], sigma="max")
    assert skewed > equal


def test_negative_penalty():
    doc = [[1.0, 0.0]]
    neg = [[1.0, 0.0], [0.0, 1.0]]
    pen = negative_penalty(doc, neg, scale=0.5)
    assert pen > 0.4


def test_mmr():
    ids = ["a", "b", "c"]
    scores = {"a": 1.0, "b": 0.9, "c": 0.8}
    vectors = {
        "a": [1.0, 0.0],
        "b": [0.99, 0.01],  # near a
        "c": [0.0, 1.0],
    }
    selected = mmr(ids, scores, vectors, k=2, lambda_=0.5)
    assert selected[0] == "a"
    assert "c" in selected  # diversity prefers c over near-duplicate b
