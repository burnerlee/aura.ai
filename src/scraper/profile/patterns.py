# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Mine what a user dislikes (or likes) about *posts*, beyond their theme.

Every explicit reaction stores a snapshot of the post's attributes: style, tone,
length, author, topic tags and so on. Per attribute we compare how often the user
skips posts that have it against how often they skip posts overall (lift). An
attribute that is skipped far more than the user's own baseline becomes an anti rule
("AI posts are fine, but not the hype ones"); the mirror case becomes an affinity.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from scraper.models.tag import TagKind
from scraper.models.user import (
    DNARule,
    DNARuleKind,
    DNARuleSource,
    InterestDNA,
    NoticedAttr,
)
from scraper.profile.dna import bump, confidence_scale
from scraper.query.rules import LONG_WORDS, SHORT_WORDS, length_bucket
from scraper.tags.vocabulary import normalize_label

MIN_SUPPORT = 3  # posts with the attribute before we say anything about it
MIN_EVIDENCE = 2  # ...of which at least this many on the relevant side
MIN_LIFT = 0.25  # rate difference vs the user's own baseline
_PRIOR = 2.0  # pseudo-observations pulling a rate toward the baseline
_STRENGTH_AT = 0.5  # lift at which a rule reaches full strength
_MAX_EVIDENCE = 5
_NOTICED_LIMIT = 4

_LENGTH_LABEL = {
    "short": f"short reads (under {SHORT_WORDS} words)",
    "medium": f"medium reads ({SHORT_WORDS}-{LONG_WORDS} words)",
    "long": f"long reads ({LONG_WORDS}+ words)",
}
# Tie-break when attributes look equally suspicious: most actionable first.
_KIND_ORDER = {
    DNARuleKind.STYLE: 0,
    DNARuleKind.LENGTH: 1,
    DNARuleKind.EMOTION: 2,
    DNARuleKind.TOPIC: 3,
    DNARuleKind.AUTHOR: 4,
    DNARuleKind.READING_LEVEL: 5,
    DNARuleKind.SOURCE: 6,
}


@dataclass(frozen=True)
class Attr:
    kind: DNARuleKind
    key: str
    label: str


@dataclass
class Observation:
    post_id: str
    positive: bool
    weight: float
    attrs: frozenset[Attr]


@dataclass
class MinedRules:
    anti: list[DNARule] = field(default_factory=list)
    affinities: list[DNARule] = field(default_factory=list)


def _word_count(raw: Mapping[str, Any]) -> int | None:
    value = raw.get("word_count")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    body = raw.get("content_text") or raw.get("content") or ""
    return len(str(body).split()) or None


def _primary_emotion(facets: Mapping[str, Any]) -> str | None:
    emotion = facets.get("emotion")
    if not isinstance(emotion, Mapping) or not emotion:
        return None
    scores = {k: v for k, v in emotion.items() if isinstance(v, (int, float))}
    if not scores or max(scores.values()) <= 0:
        return None
    return max(scores, key=lambda k: scores[k])


def build_snapshot(
    raw: Mapping[str, Any],
    *,
    theme: tuple[str, str] | None,
    matched_label: str | None,
    match_percent: float | None,
) -> dict[str, Any]:
    """Facets of a post as the user saw it, stored on the interaction."""
    facets = raw.get("facets") if isinstance(raw.get("facets"), Mapping) else {}
    author = raw.get("author") if isinstance(raw.get("author"), Mapping) else {}
    tags = [
        {"id": t["id"], "label": t.get("label") or t["id"], "kind": str(t.get("kind"))}
        for t in raw.get("canonical_tags") or []
        if isinstance(t, Mapping) and t.get("id")
    ]
    return {
        "post_id": str(raw.get("_id") or ""),
        "theme_id": theme[0] if theme else None,
        "theme_label": theme[1] if theme else None,
        "tags": tags,
        "emotion": _primary_emotion(facets or {}),
        "reading_level": (facets or {}).get("reading_level"),
        "word_count": _word_count(raw),
        "author": (author or {}).get("name") or raw.get("author_name"),
        "source": raw.get("source"),
        "matched_label": matched_label,
        "match_percent": match_percent,
    }


def attributes(snapshot: Mapping[str, Any]) -> frozenset[Attr]:
    """Minable attributes of a snapshot. The theme is excluded on purpose: theme-level
    taste already lives in the DNA weights; this is for what is *within* a theme."""
    attrs: set[Attr] = set()
    for tag in snapshot.get("tags") or []:
        kind = str(tag.get("kind"))
        if kind == TagKind.TOPIC.value:
            attrs.add(Attr(DNARuleKind.TOPIC, tag["id"], tag["label"]))
        elif kind == TagKind.STYLE.value:
            attrs.add(Attr(DNARuleKind.STYLE, tag["id"], tag["label"]))
    if snapshot.get("emotion"):
        attrs.add(Attr(DNARuleKind.EMOTION, snapshot["emotion"], f"{snapshot['emotion']} tone"))
    if snapshot.get("reading_level"):
        level = str(snapshot["reading_level"])
        attrs.add(Attr(DNARuleKind.READING_LEVEL, level, f"{level} reading level"))
    bucket = length_bucket(snapshot.get("word_count"))
    if bucket:
        attrs.add(Attr(DNARuleKind.LENGTH, bucket, _LENGTH_LABEL[bucket]))
    if snapshot.get("author"):
        name = str(snapshot["author"])
        attrs.add(Attr(DNARuleKind.AUTHOR, name, name))
    if snapshot.get("source"):
        source = str(snapshot["source"])
        attrs.add(Attr(DNARuleKind.SOURCE, source, source.title()))
    return frozenset(attrs)


def observations_from_interactions(docs: Iterable[Mapping[str, Any]]) -> list[Observation]:
    """One observation per post (newest reaction wins); needs a snapshot and a signal."""
    seen: set[str] = set()
    out: list[Observation] = []
    for doc in docs:  # newest first
        snap = doc.get("snapshot")
        post_id = str(doc.get("post_id") or "")
        weight = doc.get("weight")
        if not snap or not post_id or post_id in seen:
            continue
        # Even a neutral/undo interaction should "win" and hide older reactions for
        # this post, so toggling off a like/banish can actually remove evidence.
        seen.add(post_id)
        if not weight:
            continue
        positive = weight > 0
        out.append(
            Observation(
                post_id=post_id,
                positive=positive,
                weight=confidence_scale(positive, doc.get("match_percent")),
                attrs=attributes(snap),
            )
        )
    return out


@dataclass
class _Stat:
    n: int = 0
    negative: int = 0
    weight: float = 0.0
    negative_weight: float = 0.0
    neg_posts: list[str] = field(default_factory=list)
    pos_posts: list[str] = field(default_factory=list)


def _tally(observations: list[Observation]) -> tuple[dict[Attr, _Stat], float]:
    stats: dict[Attr, _Stat] = defaultdict(_Stat)
    total = negative_total = 0.0
    for obs in observations:
        total += obs.weight
        negative_total += 0.0 if obs.positive else obs.weight
        for attr in obs.attrs:
            stat = stats[attr]
            stat.n += 1
            stat.weight += obs.weight
            if obs.positive:
                stat.pos_posts.append(obs.post_id)
            else:
                stat.negative += 1
                stat.negative_weight += obs.weight
                stat.neg_posts.append(obs.post_id)
    baseline = negative_total / total if total else 0.0
    return stats, baseline


def _lift(stat: _Stat, baseline: float) -> float:
    """Smoothed skip-rate of posts with the attribute minus the user's overall rate."""
    rate = (stat.negative_weight + _PRIOR * baseline) / (stat.weight + _PRIOR)
    return rate - baseline


def mine_rules(
    observations: list[Observation],
    *,
    dismissed: Iterable[str] = (),
) -> MinedRules:
    """Anti rules for over-skipped attributes, affinities for over-liked ones."""
    stats, baseline = _tally(observations)
    skip = set(dismissed)
    mined = MinedRules()
    for attr, stat in stats.items():
        if stat.n < MIN_SUPPORT or f"{attr.kind.value}:{attr.key}" in skip:
            continue
        lift = _lift(stat, baseline)
        positives = stat.n - stat.negative
        if lift >= MIN_LIFT and stat.negative >= MIN_EVIDENCE:
            mined.anti.append(
                DNARule(
                    kind=attr.kind,
                    key=attr.key,
                    label=attr.label,
                    strength=round(min(1.0, lift / _STRENGTH_AT), 2),
                    source=DNARuleSource.LEARNED,
                    evidence_ids=stat.neg_posts[:_MAX_EVIDENCE],
                )
            )
        elif lift <= -MIN_LIFT and positives >= MIN_EVIDENCE:
            mined.affinities.append(
                DNARule(
                    kind=attr.kind,
                    key=attr.key,
                    label=attr.label,
                    strength=round(min(1.0, -lift / _STRENGTH_AT), 2),
                    source=DNARuleSource.LEARNED,
                    evidence_ids=stat.pos_posts[:_MAX_EVIDENCE],
                )
            )
    mined.anti.sort(key=lambda r: -r.strength)
    mined.affinities.sort(key=lambda r: -r.strength)
    return mined


def merge_mined(dna: InterestDNA, mined: MinedRules) -> tuple[InterestDNA, list[DNARule]]:
    """Replace the learned rules in ``dna`` with ``mined``.

    Chat and user-confirmed rules are never touched. Returns the DNA (version bumped
    only if something changed) and the anti rules that are new, i.e. the proposals the
    UI should ask the user about.
    """

    def merge(current: list[DNARule], fresh: list[DNARule]) -> list[DNARule]:
        kept = [r for r in current if r.source != DNARuleSource.LEARNED]
        taken = {(r.kind, r.key) for r in kept}
        return kept + [r for r in fresh if (r.kind, r.key) not in taken]

    anti = merge(dna.anti, mined.anti)
    affinities = merge(dna.affinities, mined.affinities)
    before = {(r.kind, r.key) for r in dna.anti}
    proposals = [r for r in anti if (r.kind, r.key) not in before]

    if anti == dna.anti and affinities == dna.affinities:
        return dna, []
    return bump(dna, anti=anti, affinities=affinities), proposals


def noticed_for(
    snapshot: Mapping[str, Any],
    observations: list[Observation],
    *,
    dismissed: Iterable[str] = (),
) -> list[NoticedAttr]:
    """Attributes of the just-skipped post, most suspicious first, as one-tap chips.

    With little history there is no lift to rank by, so the post's own distinctive
    attributes are offered and the user decides; each carries how often the user has
    reacted to / skipped posts like it.
    """
    stats, baseline = _tally(observations)
    skip = set(dismissed)
    ranked: list[tuple[float, int, NoticedAttr]] = []
    for attr in attributes(snapshot):
        if f"{attr.kind.value}:{attr.key}" in skip:
            continue
        stat = stats.get(attr, _Stat())
        ranked.append(
            (
                -_lift(stat, baseline) if stat.n else 0.0,
                _KIND_ORDER.get(attr.kind, 9),
                NoticedAttr(
                    kind=attr.kind,
                    key=attr.key,
                    label=attr.label,
                    seen=stat.n,
                    negative=stat.negative,
                ),
            )
        )
    ranked.sort(key=lambda r: (r[0], r[1], normalize_label(r[2].label)))
    return [item for _, _, item in ranked[:_NOTICED_LIMIT]]
