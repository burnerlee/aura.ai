# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Apply DNA anti/affinity rules to a post, and rank a score within its pool."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from scraper.models.user import DNARule, DNARuleKind, DNARuleSource
from scraper.query.types import MatchFlag, RuleSet
from scraper.tags.vocabulary import normalize_label, slugify

# Cosine fits live in a narrow band, so rule effects are small absolute amounts.
ANTI_UNIT = 0.08
ANTI_CAP = 0.20
AFFINITY_UNIT = 0.04
AFFINITY_CAP = 0.10
# A pattern the system inferred counts less than one the user stated or confirmed.
_SOURCE_FACTOR = {
    DNARuleSource.CHAT: 1.0,
    DNARuleSource.CONFIRMED: 1.0,
    DNARuleSource.LEARNED: 0.6,
}

SHORT_WORDS = 400
LONG_WORDS = 1200
MAX_PERCENT = 98
MIN_POOL_FOR_PERCENT = 5
RELIABLE_POOL = 20


def length_bucket(word_count: int | float | None) -> str | None:
    if not word_count or word_count <= 0:
        return None
    if word_count < SHORT_WORDS:
        return "short"
    return "medium" if word_count < LONG_WORDS else "long"


def _custom_keys(payload: dict[str, Any]) -> set[str]:
    """``custom:<slug>`` keys for free-form labels a post carries."""
    labels: list[Any] = [
        *(payload.get("topics") or []),
        *(payload.get("categories") or []),
        *(payload.get("tags") or []),
    ]
    return {f"custom:{slug}" for label in labels if (slug := slugify(str(label)))}


def rule_matches(rule: DNARule, payload: dict[str, Any]) -> bool:
    kind = rule.kind
    if kind in (DNARuleKind.TOPIC, DNARuleKind.STYLE):
        if rule.key in (payload.get("tag_ids") or []):
            return True
        return rule.key.startswith("custom:") and rule.key in _custom_keys(payload)
    if kind == DNARuleKind.EMOTION:
        emotion = str(payload.get("emotion_primary") or "")
        return normalize_label(rule.key) == normalize_label(emotion)
    if kind == DNARuleKind.AUTHOR:
        return normalize_label(rule.key) == normalize_label(str(payload.get("author_name") or ""))
    if kind == DNARuleKind.SOURCE:
        return rule.key == payload.get("source")
    if kind == DNARuleKind.LENGTH:
        return rule.key == length_bucket(payload.get("word_count"))
    if kind == DNARuleKind.READING_LEVEL:
        return normalize_label(rule.key) == normalize_label(str(payload.get("reading_level") or ""))
    return False


@dataclass
class RuleEffect:
    penalty: float = 0.0
    boost: float = 0.0
    flags: list[MatchFlag] = field(default_factory=list)


def _label(rule: DNARule) -> str:
    return rule.label or rule.key.split(":", 1)[-1]


def rule_effect(payload: dict[str, Any], rules: RuleSet | None) -> RuleEffect:
    """Fit adjustment from the user's anti/affinity rules that this post trips."""
    effect = RuleEffect()
    if rules is None:
        return effect
    for rule in rules.anti:
        if rule_matches(rule, payload):
            effect.penalty += ANTI_UNIT * rule.strength * _SOURCE_FACTOR[rule.source]
            effect.flags.append(MatchFlag(kind="aversion", label=_label(rule), rule_key=rule.key))
    for rule in rules.affinities:
        if rule_matches(rule, payload):
            effect.boost += AFFINITY_UNIT * rule.strength * _SOURCE_FACTOR[rule.source]
            effect.flags.append(MatchFlag(kind="affinity", label=_label(rule), rule_key=rule.key))
    effect.penalty = min(ANTI_CAP, effect.penalty)
    effect.boost = min(AFFINITY_CAP, effect.boost)
    return effect


def percentile_rank(value: float, pool: Sequence[float]) -> float:
    """Mid-rank percentile in [0, 100]; ties share the average rank."""
    if not pool:
        return 0.0
    below = sum(1 for v in pool if v < value)
    equal = sum(1 for v in pool if v == value)
    return (below + 0.5 * equal) / len(pool) * 100.0


def match_percent(value: float, pool: Sequence[float]) -> int | None:
    """Relative match, or None when the pool is too small to mean anything.

    Capped below 100: the best candidate in any pool is the 100th percentile by
    construction, and "100% match" on every feed would be noise.
    """
    if len(pool) < MIN_POOL_FOR_PERCENT:
        return None
    return round(min(float(MAX_PERCENT), percentile_rank(value, pool)))
