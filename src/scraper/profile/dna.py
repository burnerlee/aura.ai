# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Server-owned Interest DNA: build from chat, seed, import, patch, reconcile. No I/O."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from scraper.models.tag import TagKind
from scraper.models.user import (
    DNAPatch,
    DNARule,
    DNARuleKind,
    DNARuleSource,
    InterestDNA,
    UserProfile,
)
from scraper.profile.aura import AuraProfileDraft
from scraper.tags.vocabulary import TagResolver, slugify

CUSTOM_PREFIX = "custom:"
MAX_KEYS = 24
_FLOOR = 0.025
_NEW_THEME_WEIGHT = 8.0
_ANTI_CAP = 5.0
# Same bounds the browser used for one theme: never fully erased, never dominant.
_MIN_SHARE = 2.5
_MAX_SHARE = 80.0
# One strong Resonate/Banish moves a theme by this many points (weight 1.0).
DNA_STEP = 7.0
_MAX_SEED_TOPICS = 8
# ``compute_centroids`` names clusters interest_0, interest_1, ...: placeholders, not themes.
_SYNTHETIC_LABEL = re.compile(r"^interest[\s_-]*\d+$", re.IGNORECASE)

# Browser-side seed theme ids -> a phrase the tag resolver can match.
_SEED_HINTS = {
    "ai": "artificial intelligence",
    "cyberpunk": "cyberpunk",
    "space": "space and astronomy",
    "culture": "indie music and culture",
}


class DNAVersionConflict(Exception):
    """The caller edited a stale copy of the DNA."""

    def __init__(self, current_version: int) -> None:
        super().__init__(f"DNA version conflict (current={current_version})")
        self.current_version = current_version


def normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    """Scale to a 0-100 distribution (1 decimal); mirrors the UI's old normalizeVector."""
    if not raw:
        return {}
    capped = dict(sorted(raw.items(), key=lambda kv: -kv[1])[:MAX_KEYS])
    safe = {k: max(_FLOOR, _finite(v)) for k, v in capped.items()}
    total = sum(safe.values())
    rounded = {k: round(v / total * 100, 1) for k, v in safe.items()}
    first = next(iter(rounded))
    rounded[first] = round(rounded[first] + (100 - sum(rounded.values())), 1)
    return rounded


def _finite(value: float) -> float:
    number = float(value)
    return number if math.isfinite(number) else 0.0


def humanize(label: str) -> str:
    """``practical-ai`` -> ``practical ai``; leaves already-spaced/cased labels alone."""
    clean = label.strip()
    if clean and " " not in clean and clean == clean.lower():
        return clean.replace("-", " ").replace("_", " ")
    return clean


def label_for_key(key: str, labels: dict[str, str], resolver: TagResolver | None) -> str:
    if key in labels:
        return labels[key]
    if resolver is not None:
        tag = resolver.by_id(key)
        if tag is not None:
            return tag.label
    return humanize(key.split(":", 1)[-1])


def _theme_key(label: str, resolver: TagResolver | None) -> tuple[str, str] | None:
    """Theme id for a free-form label (any known topic label resolves), else custom."""
    clean = label.strip()
    if not clean:
        return None
    tag = resolver.resolve(clean, TagKind.THEME) if resolver is not None else None
    if tag is not None:
        return tag.id, tag.label
    slug = slugify(clean)
    if not slug:
        return None
    return f"{CUSTOM_PREFIX}{slug}", humanize(clean)


def bump(dna: InterestDNA, **changes: object) -> InterestDNA:
    """Copy with ``changes`` applied, version incremented, timestamp refreshed."""
    return dna.model_copy(
        update={**changes, "version": dna.version + 1, "updated_at": datetime.now(UTC)}
    )


def build_dna_from_draft(
    draft: AuraProfileDraft,
    resolver: TagResolver | None,
    *,
    previous: InterestDNA | None = None,
) -> InterestDNA:
    """DNA from Aura's drafted profile, keyed by canonical tags.

    Chat-sourced anti rules are replaced by the new draft; rules mined from feedback
    (``learned`` / ``confirmed``) and affinities carry over from ``previous``.
    """
    prev = previous or InterestDNA()
    labels: dict[str, str] = {}
    raw: dict[str, float] = {}

    if draft.theme_weights:
        entries = list(draft.theme_weights.items())
    else:
        entries = [(t, max(5.0, 90.0 - i * 12.0)) for i, t in enumerate(draft.themes)]
    for theme, weight in entries:
        resolved = _theme_key(theme, resolver)
        if resolved is None:
            continue
        key, display = resolved
        labels[key] = display
        raw[key] = raw.get(key, 0.0) + max(1.0, _finite(weight))

    anti: list[DNARule] = []
    anti_keys: set[str] = set()
    for topic in draft.anti_topics:
        resolved = _theme_key(topic, resolver)
        if resolved is None or resolved[0] in anti_keys:
            continue
        key, display = resolved
        anti_keys.add(key)
        if key in raw:
            raw[key] = min(raw[key], _ANTI_CAP)
        anti.append(
            DNARule(
                kind=DNARuleKind.TOPIC,
                key=key,
                label=display,
                strength=1.0,
                source=DNARuleSource.CHAT,
            )
        )

    weights = normalize_weights(raw)
    # Themes listed without a weight still earn a small share (but never an avoided one).
    added = False
    for theme in draft.themes:
        resolved = _theme_key(theme, resolver)
        if resolved is None or resolved[0] in weights or resolved[0] in anti_keys:
            continue
        weights[resolved[0]] = _NEW_THEME_WEIGHT
        labels[resolved[0]] = resolved[1]
        added = True
    if added:
        weights = normalize_weights(weights)

    if not weights:
        # Draft carried no themes: keep what we had rather than blanking the ring.
        weights = dict(prev.weights)
        labels = dict(prev.labels)

    carried = [r for r in prev.anti if r.source != DNARuleSource.CHAT and r.key not in anti_keys]
    anti.extend(carried)
    for rule in (*anti, *prev.affinities):
        if rule.kind == DNARuleKind.TOPIC and rule.key not in labels and rule.label:
            labels[rule.key] = rule.label

    return bump(
        prev,
        weights=weights,
        labels={k: v for k, v in labels.items() if k in weights or k in {r.key for r in anti}},
        anti=anti,
        prompt=(draft.prompt or "").strip() or prev.prompt,
    )


def seed_dna(profile: UserProfile, resolver: TagResolver | None) -> InterestDNA | None:
    """One-time migration for profiles that predate server-side DNA.

    Seeds weights from the persona's topics (ordered, decaying) plus labelled interest
    centroids. Returns None when there is nothing to seed from.
    """
    persona = profile.persona
    entries: dict[str, float] = {}
    for i, topic in enumerate(persona.topics[:_MAX_SEED_TOPICS]):
        entries.setdefault(topic, max(10.0, 90.0 - i * 12.0))
    for centroid in profile.interest_centroids:
        if centroid.label and not _SYNTHETIC_LABEL.match(centroid.label):
            entries.setdefault(centroid.label, 40.0 * max(0.1, centroid.weight))
    if not entries:
        return None
    draft = AuraProfileDraft(
        prompt=persona.summary,
        anti_topics=list(persona.anti_topics[:_MAX_SEED_TOPICS]),
        theme_weights=entries,
    )
    return build_dna_from_draft(draft, resolver, previous=profile.dna)


def import_vector(
    vector: dict[str, float],
    *,
    prompt: str,
    excluded: list[str],
    resolver: TagResolver | None,
    previous: InterestDNA | None = None,
) -> InterestDNA | None:
    """One-time import of the DNA the browser kept in localStorage."""
    def theme_label(key: str) -> str:
        # The browser's four seed ids mean something specific ("culture" was "indie pop
        # & culture", not "company culture"), so their descriptive hint always wins.
        # Any other key is a label the corpus may already know.
        return _SEED_HINTS.get(key, humanize(key))

    entries = {
        theme_label(key): _finite(weight) for key, weight in vector.items() if _finite(weight) > 0
    }
    if not entries:
        return None
    draft = AuraProfileDraft(
        prompt=prompt,
        anti_topics=[theme_label(k) for k in excluded],
        theme_weights=entries,
    )
    return build_dna_from_draft(draft, resolver, previous=previous)


def adjust_weight(
    dna: InterestDNA,
    key: str,
    label: str,
    delta: float,
) -> InterestDNA:
    """Move one theme by ``delta`` points; every other theme rescales to keep 100.

    The server-side replacement for the browser's ``adjustInterestVector``.
    """
    if key not in dna.weights and delta <= 0:
        return dna  # nothing to reduce: a dislike must not conjure a theme into the DNA
    current = {k: max(0.1, v) for k, v in dna.weights.items()}
    current.setdefault(key, _NEW_THEME_WEIGHT)
    target = min(_MAX_SHARE, max(_MIN_SHARE, current[key] + delta))
    others = {k: v for k, v in current.items() if k != key}
    remaining = 100.0 - target
    other_total = sum(others.values())
    if others and other_total > 0:
        scaled = {k: v / other_total * remaining for k, v in others.items()}
    else:
        scaled = {}
    weights = normalize_weights({**scaled, key: target})
    labels = {**dna.labels, key: dna.labels.get(key, label)}
    return bump(dna, weights=weights, labels={k: v for k, v in labels.items() if k in weights})


def confidence_scale(positive: bool, match_percent: float | None) -> float:
    """How much a piece of feedback should count given how sure the match looked.

    A banish on a 95% match was a confident miss (counts more); a banish on a 40% match
    was expected. For likes it is the reverse: a like on a low match is the surprise.
    """
    if match_percent is None:
        return 1.0
    pct = min(100.0, max(0.0, match_percent))
    shift = (pct - 50.0) / 100.0
    return 1.0 + (-shift if positive else shift)


def apply_patch(
    dna: InterestDNA,
    patch: DNAPatch,
    *,
    resolver: TagResolver | None = None,
) -> InterestDNA:
    """Apply a manual edit. ``set_weights`` are target percentages; the rest rescale."""
    if patch.base_version != dna.version:
        raise DNAVersionConflict(dna.version)

    weights = {k: v for k, v in dna.weights.items() if k not in set(patch.remove_weights)}
    labels = dict(dna.labels)
    if patch.set_weights:
        targets = {k: min(95.0, max(0.0, _finite(v))) for k, v in patch.set_weights.items()}
        for key in targets:
            labels.setdefault(key, label_for_key(key, labels, resolver))
        others = {k: v for k, v in weights.items() if k not in targets}
        remaining = max(0.0, 100.0 - sum(targets.values()))
        other_total = sum(others.values())
        scaled = (
            {k: v / other_total * remaining for k, v in others.items()} if other_total > 0 else {}
        )
        weights = {**scaled, **targets}
    weights = normalize_weights(weights)

    removed = set(patch.remove_anti)
    anti = [r for r in dna.anti if r.key not in removed]
    dismissed = list(dna.dismissed)
    for rule in dna.anti:
        marker = f"{rule.kind.value}:{rule.key}"
        if rule.key in removed and marker not in dismissed:
            dismissed.append(marker)  # never propose this again
    index = {(r.kind, r.key): i for i, r in enumerate(anti)}
    for rule in patch.add_anti:
        confirmed = rule.model_copy(update={"source": DNARuleSource.CONFIRMED})
        pos = index.get((rule.kind, rule.key))
        if pos is None:
            index[(rule.kind, rule.key)] = len(anti)
            anti.append(confirmed)
        elif anti[pos].source == DNARuleSource.LEARNED:
            # Accepting a proposal keeps its evidence and strength, drops the doubt.
            anti[pos] = anti[pos].model_copy(update={"source": DNARuleSource.CONFIRMED})
        marker = f"{rule.kind.value}:{rule.key}"
        dismissed = [m for m in dismissed if m != marker]

    return bump(
        dna,
        weights=weights,
        labels={k: v for k, v in labels.items() if k in weights},
        anti=anti,
        dismissed=dismissed,
        prompt=dna.prompt if patch.prompt is None else patch.prompt.strip(),
    )


def reconcile(dna: InterestDNA, resolver: TagResolver | None) -> tuple[InterestDNA, bool]:
    """Follow ``merged_into`` links and refresh labels after a tag-vocabulary rebuild.

    Lifts legacy topic keys to their parent theme and promotes ``custom:`` themes whose
    label now exactly matches a known theme or topic label.
    Returns ``(dna, changed)``; the version only moves when something changed.
    """
    if resolver is None or not dna.weights:
        return dna, False

    def remap(key: str) -> tuple[str, str]:
        if key.startswith(CUSTOM_PREFIX):
            label = dna.labels.get(key) or humanize(key[len(CUSTOM_PREFIX) :])
            tag = resolver.resolve(label, TagKind.THEME)
        else:
            tag = resolver.by_id(key)
            label = dna.labels.get(key, "")
            if tag is not None and tag.kind == TagKind.TOPIC and tag.parent_id:
                # Keys written before themes existed: lift topics to their theme.
                tag = resolver.by_id(tag.parent_id) or tag
        if tag is not None:
            return tag.id, tag.label
        return key, label or label_for_key(key, dna.labels, resolver)

    weights: dict[str, float] = {}
    labels: dict[str, str] = {}
    for key, weight in dna.weights.items():
        new_key, label = remap(key)
        weights[new_key] = weights.get(new_key, 0.0) + weight
        labels[new_key] = label

    def remap_rule(rule: DNARule) -> DNARule:
        # Topic rules may target a theme, a fine topic tag, or a custom label; only
        # theme/custom keys are remapped (a fine topic rule stays fine).
        if rule.kind != DNARuleKind.TOPIC or rule.key.startswith(("topic:", "style:")):
            return rule
        new_key, label = remap(rule.key)
        return rule.model_copy(update={"key": new_key, "label": label or rule.label})

    anti = [remap_rule(r) for r in dna.anti]
    affinities = [remap_rule(r) for r in dna.affinities]

    changed = (
        weights != dna.weights
        or labels != dna.labels
        or anti != dna.anti
        or affinities != dna.affinities
    )
    if not changed:
        return dna, False
    healed = bump(
        dna,
        weights=normalize_weights(weights),
        labels=labels,
        anti=anti,
        affinities=affinities,
    )
    return healed, True
