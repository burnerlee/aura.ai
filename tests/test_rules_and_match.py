# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Rule matching, relative match percent, and the match object the engine returns."""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from scraper.models.user import DNARule, DNARuleKind, DNARuleSource
from scraper.query.engine import RecommendationEngine
from scraper.query.rules import (
    ANTI_CAP,
    length_bucket,
    match_percent,
    percentile_rank,
    rule_effect,
    rule_matches,
)
from scraper.query.types import QueryKind, QuerySet, QueryVector, RuleSet


class FakeVectors:
    """Cosine ANN over in-memory points (same shape the engine expects from Qdrant)."""

    def __init__(self, points: dict[str, dict]) -> None:
        self.points = points

    def search(self, vector_name, vector, *, k=10, filt=None, exclude_ids=None):
        exclude = set(exclude_ids or [])
        q = np.asarray(vector, dtype=np.float32)
        q = q / max(float(np.linalg.norm(q)), 1e-12)
        scored = []
        for pid, data in self.points.items():
            if pid in exclude:
                continue
            doc = np.asarray(data["doc"], dtype=np.float32)
            doc = doc / max(float(np.linalg.norm(doc)), 1e-12)
            scored.append(SimpleNamespace(id=pid, score=float(q @ doc), payload=data["payload"]))
        scored.sort(key=lambda p: -p.score)
        return scored[:k]

    def fetch(self, ids, *, with_vectors=False):
        return [
            SimpleNamespace(
                id=pid,
                payload=self.points[pid]["payload"],
                vector={"chunks": self.points[pid]["chunks"], "doc": self.points[pid]["doc"]},
            )
            for pid in ids
            if pid in self.points
        ]


def _rule(kind, key, *, source=DNARuleSource.CONFIRMED, strength=1.0, label=None) -> DNARule:
    return DNARule(kind=kind, key=key, strength=strength, source=source, label=label)


PAYLOAD = {
    "tag_ids": ["theme:ai", "topic:llms", "style:listicle"],
    "topics": ["LLMs"],
    "categories": ["Hype Cycle"],
    "emotion_primary": "excitement",
    "author_name": "Jane Roe",
    "source": "substack",
    "word_count": 1500,
    "reading_level": "Advanced",
}


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (_rule(DNARuleKind.TOPIC, "theme:ai"), True),
        (_rule(DNARuleKind.TOPIC, "theme:space"), False),
        (_rule(DNARuleKind.STYLE, "style:listicle"), True),
        (_rule(DNARuleKind.STYLE, "style:analytical"), False),
        (_rule(DNARuleKind.TOPIC, "custom:hype-cycle"), True),  # free-form chat theme
        (_rule(DNARuleKind.TOPIC, "custom:llms"), True),
        (_rule(DNARuleKind.EMOTION, "Excitement"), True),
        (_rule(DNARuleKind.EMOTION, "sadness"), False),
        (_rule(DNARuleKind.AUTHOR, "jane roe"), True),
        (_rule(DNARuleKind.SOURCE, "substack"), True),
        (_rule(DNARuleKind.SOURCE, "reddit"), False),
        (_rule(DNARuleKind.LENGTH, "long"), True),
        (_rule(DNARuleKind.LENGTH, "short"), False),
        (_rule(DNARuleKind.READING_LEVEL, "advanced"), True),
    ],
)
def test_rule_matching(rule, expected):
    assert rule_matches(rule, PAYLOAD) is expected


def test_length_buckets():
    assert [length_bucket(n) for n in (None, 0, 399, 400, 1199, 1200)] == [
        None,
        None,
        "short",
        "medium",
        "medium",
        "long",
    ]


def test_rule_effect_scales_by_source_and_strength_and_caps():
    rules = RuleSet(
        anti=[
            _rule(DNARuleKind.STYLE, "style:listicle", label="listicle"),
            _rule(DNARuleKind.LENGTH, "long", source=DNARuleSource.LEARNED, strength=0.5),
        ],
        affinities=[_rule(DNARuleKind.AUTHOR, "jane roe", label="Jane Roe")],
    )
    effect = rule_effect(PAYLOAD, rules)
    assert effect.penalty == pytest.approx(0.08 * 1.0 + 0.08 * 0.5 * 0.6)
    assert effect.boost == pytest.approx(0.04)
    assert [(f.kind, f.label) for f in effect.flags] == [
        ("aversion", "listicle"),
        ("aversion", "long"),
        ("affinity", "Jane Roe"),
    ]

    many = RuleSet(anti=[_rule(DNARuleKind.TOPIC, "theme:ai") for _ in range(10)])
    assert rule_effect(PAYLOAD, many).penalty == ANTI_CAP
    assert rule_effect(PAYLOAD, None).penalty == 0.0


def test_percentile_rank_uses_mid_rank_for_ties():
    pool = [1.0, 2.0, 2.0, 3.0]
    assert percentile_rank(1.0, pool) == 12.5
    assert percentile_rank(2.0, pool) == 50.0
    assert percentile_rank(3.0, pool) == 87.5
    assert percentile_rank(1.0, []) == 0.0


def test_match_percent_caps_the_top_and_withholds_tiny_pools():
    pool = [float(i) for i in range(100)]
    assert match_percent(99.0, pool) == 98  # best candidate is never "100%"
    assert match_percent(0.0, pool) == 0
    assert 49 <= match_percent(50.0, pool) <= 51
    assert match_percent(1.0, [1.0, 2.0, 3.0]) is None


def _points(n: int = 24) -> dict[str, dict]:
    """n posts fanned between the x and y axes; post i leans toward y as i grows."""
    points: dict[str, dict] = {}
    for i in range(n):
        y = i / (n - 1)
        vec = [1.0 - y, y]
        points[f"p{i}"] = {
            "doc": vec,
            "chunks": [vec],
            "payload": {
                "post_id": f"p{i}",
                "title": f"Post {i}",
                "author_name": f"author-{i}",
                "published_at": None,
                "tag_ids": ["style:listicle"] if i == 0 else [],
            },
        }
    return points


def _engine() -> RecommendationEngine:
    engine = RecommendationEngine(vectors=FakeVectors(_points()))  # type: ignore[arg-type]
    engine.settings.filter_k = 50
    engine.settings.author_diversity_cap = 5
    engine.settings.mmr_lambda = 1.0
    return engine


def _qs() -> QuerySet:
    return QuerySet(vectors=[QueryVector(vector=[1.0, 0.0], kind=QueryKind.THEME, label="Space")])


def test_engine_match_is_relative_to_the_whole_scored_pool_not_the_shown_list():
    results = _engine().recommend(_qs(), k=3)
    top = results[0]
    assert top.post_id == "p0"
    assert top.match is not None
    assert top.match.pool_size == 24 and top.match.reliable
    assert top.match.percent == 98  # best of 24, capped
    # Third place of 3 shown is still near the top of the pool of 24.
    assert results[2].match.percent > 85
    assert top.match.top_attribution == "Space"
    assert top.match.components["semantic"] > results[2].match.components["semantic"]
    assert top.match.flags == []


def test_engine_small_pool_has_no_percent_and_is_unreliable():
    engine = RecommendationEngine(vectors=FakeVectors(dict(list(_points().items())[:3])))  # type: ignore[arg-type]
    engine.settings.filter_k = 50
    results = engine.recommend(_qs(), k=3)
    assert all(r.match.percent is None for r in results)
    assert not results[0].match.reliable


def test_engine_aversion_rule_lowers_fit_flags_it_and_moves_the_percent():
    engine = _engine()
    plain = {r.post_id: r for r in engine.recommend(_qs(), k=24)}
    rules = RuleSet(
        anti=[_rule(DNARuleKind.STYLE, "style:listicle", label="listicle", strength=1.0)]
    )
    ruled = {r.post_id: r for r in engine.recommend(_qs(), k=24, rules=rules)}

    assert ruled["p0"].match.fit == pytest.approx(plain["p0"].match.fit - 0.08)
    assert ruled["p0"].match.percent < plain["p0"].match.percent
    assert ruled["p0"].match.components["aversion"] == pytest.approx(-0.08)
    assert [(f.kind, f.label) for f in ruled["p0"].match.flags] == [("aversion", "listicle")]
    # Everything else is untouched.
    assert ruled["p5"].match.fit == pytest.approx(plain["p5"].match.fit)
    assert ruled["p5"].match.flags == []


def _cone_points() -> dict[str, dict]:
    """3D posts around the query axis (z). A tight cluster of near-duplicates has the
    best fit; a ring of mutually different posts has a slightly worse fit."""
    def vec(theta_deg: float, phi_deg: float) -> list[float]:
        th, ph = math.radians(theta_deg), math.radians(phi_deg)
        return [math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)]

    points: dict[str, dict] = {}
    for i in range(12):  # cluster: fit ~0.98, all but identical to one another
        points[f"cluster{i}"] = _point(f"cluster{i}", vec(10 + i * 0.1, i * 0.5))
    for i in range(12):  # ring: fit ~0.97, spread around the axis
        points[f"ring{i}"] = _point(f"ring{i}", vec(14.0, i * 30.0))
    return points


def _point(pid: str, vec: list[float]) -> dict:
    return {
        "doc": vec,
        "chunks": [vec],
        "payload": {"post_id": pid, "title": pid, "author_name": pid, "published_at": None},
    }


def test_mmr_does_not_let_diversity_swamp_a_compressed_fit_band():
    engine = RecommendationEngine(vectors=FakeVectors(_cone_points()))  # type: ignore[arg-type]
    engine.settings.filter_k = 50
    engine.settings.author_diversity_cap = 5
    engine.settings.mmr_lambda = 0.7  # the shipped default
    qs = QuerySet(vectors=[QueryVector(vector=[0.0, 0.0, 1.0], kind=QueryKind.THEME, label="z")])

    shown = engine.recommend(qs, k=5)
    # Raw cosines span ~0.01 here, so a raw-score MMR would take the ring's variety over
    # the clearly better-fitting cluster. Percent and order must agree.
    assert all(r.post_id.startswith("cluster") for r in shown)
    percents = [r.match.percent for r in shown]
    assert percents == sorted(percents, reverse=True)
