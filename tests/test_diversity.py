# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.query.engine import RecommendationEngine


def test_cap_by_value_preserves_order_and_caps() -> None:
    ordered = ["a", "b", "c", "d", "e", "f"]
    values = {
        "a": "substack",
        "b": "substack",
        "c": "reddit",
        "d": "substack",
        "e": "reddit",
        "f": "reddit",
    }
    capped = RecommendationEngine._cap_by_value(ordered, values, cap=2)
    assert capped == ["a", "b", "c", "e"]


def test_cap_by_value_zero_or_negative_is_noop() -> None:
    ordered = ["a", "b"]
    values = {"a": "x", "b": "x"}
    assert RecommendationEngine._cap_by_value(ordered, values, cap=0) == ordered
    assert RecommendationEngine._cap_by_value(ordered, values, cap=-1) == ordered

