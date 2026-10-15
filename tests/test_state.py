# Copyright (c) 2026 DevRev Inc. All rights reserved.

import numpy as np

from scraper.profile.state import softmax_attention_weights, update_state


def test_single_like_near_item():
    item = [1.0, 0.0, 0.0]
    state = update_state([], liked=True, new_item=item)
    assert state is not None
    assert abs(np.dot(state, item / np.linalg.norm(item)) - 1.0) < 1e-5


def test_softmax_weights_sum_to_one():
    q = [1.0, 0.0]
    keys = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]
    w = softmax_attention_weights(q, keys)
    assert abs(sum(w) - 1.0) < 1e-6
    assert w[0] == max(w)


def test_mean_fallback_when_not_liked():
    positives = [[1.0, 0.0], [0.0, 1.0]]
    state = update_state(positives, liked=False)
    assert state is not None
    assert abs(state[0] - state[1]) < 1e-5
