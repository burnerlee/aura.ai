# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.models.user import EventType, FeedbackReason, Interaction, Persona
from scraper.profile.weights import (
    apply_reason_actions,
    compute_weight,
    is_explicit_negative,
    weight_default,
    weight_hold_linear,
)


def test_like_strength_levels():
    weak = Interaction(user_id="u", post_id="p", event=EventType.LIKE, strength=1)
    strong = Interaction(user_id="u", post_id="p", event=EventType.LIKE, strength=2)
    assert weight_default(weak) == 0.7
    assert weight_default(strong) == 1.0


def test_dwell_read_ratio():
    low = Interaction(
        user_id="u", post_id="p", event=EventType.DWELL, dwell_ms=1000, read_ratio=0.1
    )
    high = Interaction(
        user_id="u", post_id="p", event=EventType.DWELL, dwell_ms=10000, read_ratio=0.8
    )
    assert weight_default(low) == 0.0
    assert abs(weight_default(high) - 0.48) < 1e-6


def test_fast_skip():
    skip = Interaction(
        user_id="u", post_id="p", event=EventType.IMPRESSION, visible_ms=400
    )
    assert weight_default(skip) == -0.1


def test_hold_ms_not_used_by_default():
    a = Interaction(
        user_id="u", post_id="p", event=EventType.LIKE, strength=1, hold_ms=100
    )
    b = Interaction(
        user_id="u", post_id="p", event=EventType.LIKE, strength=1, hold_ms=5000
    )
    assert weight_default(a) == weight_default(b)
    assert weight_hold_linear(b) > weight_hold_linear(a)


def test_explicit_negative_and_reason():
    ni = Interaction(
        user_id="u",
        post_id="p",
        event=EventType.NOT_INTERESTED,
        reason=FeedbackReason.TOO_LONG,
    )
    assert is_explicit_negative(ni)
    persona = apply_reason_actions(Persona(), ni)
    assert persona.max_words == 1500


def test_compute_weight_versions():
    i = Interaction(user_id="u", post_id="p", event=EventType.SAVE)
    assert compute_weight(i, version="default") == 1.0
