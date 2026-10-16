# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Pure tag-vocabulary logic: normalize, cluster, resolve. No I/O."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from scraper.models.tag import Tag, TagKind, TagRef

logger = logging.getLogger(__name__)

# Labels too vague to be useful as a theme or a DNA key.
GENERIC_LABELS = frozenset(
    {
        "newsletter",
        "podcast",
        "blog",
        "article",
        "post",
        "general",
        "misc",
        "other",
    }
)

MAX_LABEL_LEN = 64
DEFAULT_THRESHOLD = 0.85
MAX_TOPIC_TAGS_PER_POST = 5
MAX_STYLE_TAGS_PER_POST = 2

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)

EmbedFn = Callable[[str], list[float]]


def normalize_label(label: str) -> str:
    """Lowercase, ``&`` -> ``and``, punctuation/hyphens -> single spaces."""
    text = label.strip().lower().replace("&", " and ")
    return _NON_WORD.sub(" ", text).strip()


def slugify(label: str) -> str:
    return normalize_label(label).replace(" ", "-")


def make_tag_id(kind: TagKind, label: str) -> str | None:
    slug = slugify(label)
    return f"{kind.value}:{slug}" if slug else None


def is_usable_label(label: str) -> bool:
    norm = normalize_label(label)
    return bool(norm) and norm not in GENERIC_LABELS and len(norm) <= MAX_LABEL_LEN


def _unit(vector: Sequence[float]) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 1e-12 else arr


@dataclass(frozen=True)
class CollapsedLabel:
    """Raw labels that normalize to the same string, merged."""

    label: str  # display form (most frequent raw casing)
    normalized: str
    count: int


def collapse_labels(raw_counts: Mapping[str, int]) -> list[CollapsedLabel]:
    """Merge labels that differ only by case / punctuation ("AI", "ai", "A.I.")."""
    groups: dict[str, Counter[str]] = {}
    for raw, count in raw_counts.items():
        norm = normalize_label(raw)
        if not norm:
            continue
        groups.setdefault(norm, Counter())[raw.strip()] += int(count)
    out: list[CollapsedLabel] = []
    for norm, variants in groups.items():
        # Most frequent wins; prefer a cased form over all-lowercase on ties.
        display = max(variants, key=lambda v: (variants[v], v != v.lower(), v))
        out.append(
            CollapsedLabel(label=display, normalized=norm, count=sum(variants.values()))
        )
    return out


@dataclass
class LabelEntry:
    label: str
    count: int
    vector: list[float] = field(default_factory=list)


def build_tags(
    kind: TagKind,
    entries: Sequence[LabelEntry],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    preferred: Collection[str] = (),
) -> list[Tag]:
    """Greedy leader clustering of labels by embedding cosine.

    Labels are visited with already-canonical ones first (``preferred`` holds their
    normalized forms), then by document frequency. Each label joins the first cluster
    whose canonical vector is within ``threshold``; otherwise it seeds a new cluster.
    Putting existing canonicals first keeps tag ids stable across rebuilds.
    """
    preferred_set = set(preferred)
    ordered = sorted(
        (e for e in entries if e.vector and make_tag_id(kind, e.label)),
        key=lambda e: (
            0 if normalize_label(e.label) in preferred_set else 1,
            -e.count,
            e.label.lower(),
        ),
    )
    leaders: list[np.ndarray] = []
    clusters: list[list[LabelEntry]] = []
    for entry in ordered:
        vec = _unit(entry.vector)
        if leaders:
            sims = np.stack(leaders) @ vec
            best = int(np.argmax(sims))
            if float(sims[best]) >= threshold:
                clusters[best].append(entry)
                continue
        leaders.append(vec)
        clusters.append([entry])

    tags: list[Tag] = []
    for members in clusters:
        canonical = members[0]
        tag_id = make_tag_id(kind, canonical.label)
        assert tag_id is not None  # filtered above
        canonical_norm = normalize_label(canonical.label)
        aliases = sorted(
            {normalize_label(m.label) for m in members} - {canonical_norm}
        )
        tags.append(
            Tag(
                id=tag_id,
                kind=kind,
                label=canonical.label,
                aliases=aliases,
                doc_count=sum(m.count for m in members),
                embedding=[float(x) for x in canonical.vector],
            )
        )
    return tags


class TagResolver:
    """Map free-form labels to canonical tags.

    Order: exact normalized alias match, then (optionally) nearest canonical tag by
    embedding cosine above the kind's threshold. Embedding results are cached per
    instance.

    Themes are resolved through their *topics*: a label is compared to the fine-grained
    topic tags and takes the nearest topic's parent theme. Comparing a short label to a
    theme centroid does not work: a centroid of unrelated topics sits vaguely close to
    everything, so real matches and unrelated labels score the same.
    """

    def __init__(
        self,
        tags: Iterable[Tag],
        *,
        embed_fn: EmbedFn | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        theme_threshold: float | None = None,
    ) -> None:
        self._embed_fn = embed_fn
        self._thresholds = {kind: threshold for kind in TagKind}
        if theme_threshold is not None:
            self._thresholds[TagKind.THEME] = theme_threshold
        self._by_id: dict[str, Tag] = {}
        self._alias: dict[tuple[TagKind, str], Tag] = {}
        self._cache: dict[tuple[TagKind, str], Tag | None] = {}
        live: list[Tag] = []
        for tag in tags:
            self._by_id[tag.id] = tag
            if tag.merged_into is None:
                live.append(tag)
        # Aliases first so a canonical label always wins a collision.
        for tag in live:
            for form in tag.aliases:
                self._alias[(tag.kind, normalize_label(form))] = tag
        for tag in live:
            self._alias[(tag.kind, normalize_label(tag.label))] = tag
        self._matrix: dict[TagKind, tuple[np.ndarray, list[Tag]]] = {}
        for kind in (TagKind.TOPIC, TagKind.STYLE):
            members = [t for t in live if t.kind == kind and t.embedding]
            if members:
                self._matrix[kind] = (np.stack([_unit(t.embedding) for t in members]), members)
        rows: list[np.ndarray] = []
        parents: list[Tag] = []
        for topic in live:
            if topic.kind != TagKind.TOPIC or not topic.embedding or not topic.parent_id:
                continue
            parent = self.by_id(topic.parent_id)
            if parent is not None and parent.kind == TagKind.THEME:
                rows.append(_unit(topic.embedding))
                parents.append(parent)
        if rows:
            self._matrix[TagKind.THEME] = (np.stack(rows), parents)

    def __len__(self) -> int:
        return len(self._by_id)

    def by_id(self, tag_id: str) -> Tag | None:
        """Look up a tag, following ``merged_into`` links (bounded)."""
        tag = self._by_id.get(tag_id)
        for _ in range(4):
            if tag is None or tag.merged_into is None:
                return tag
            tag = self._by_id.get(tag.merged_into)
        return tag

    def resolve(self, label: str, kind: TagKind = TagKind.TOPIC) -> Tag | None:
        if not is_usable_label(label):
            return None
        norm = normalize_label(label)
        hit = self._alias.get((kind, norm))
        if hit is not None:
            return hit
        key = (kind, norm)
        if key in self._cache:
            return self._cache[key]
        matrix = self._matrix.get(kind)
        if self._embed_fn is None or matrix is None:
            return None
        try:
            vec = _unit(self._embed_fn(label))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tag resolve embed failed for %r: %s", label, exc)
            return None
        sims = matrix[0] @ vec
        best = int(np.argmax(sims))
        found = matrix[1][best] if float(sims[best]) >= self._thresholds[kind] else None
        self._cache[key] = found
        return found

    def resolve_many(
        self,
        labels: Iterable[str],
        kind: TagKind = TagKind.TOPIC,
        *,
        limit: int | None = None,
    ) -> list[Tag]:
        out: list[Tag] = []
        seen: set[str] = set()
        for label in labels:
            tag = self.resolve(str(label), kind)
            if tag is None or tag.id in seen:
                continue
            seen.add(tag.id)
            out.append(tag)
            if limit is not None and len(out) >= limit:
                break
        return out


def tag_refs_for_facets(facets: Mapping[str, Any] | None, resolver: TagResolver) -> list[TagRef]:
    """Canonical tags for a post's stored facets: themes, then topics, then styles.

    Themes are the parents of the resolved topics (deduped, in topic order), so the
    first theme is the post's primary one.
    """
    if not facets:
        return []
    topics = resolver.resolve_many(
        facets.get("topics") or [], TagKind.TOPIC, limit=MAX_TOPIC_TAGS_PER_POST
    )
    styles = resolver.resolve_many(
        facets.get("style") or [], TagKind.STYLE, limit=MAX_STYLE_TAGS_PER_POST
    )
    themes: list[Tag] = []
    for topic in topics:
        parent = resolver.by_id(topic.parent_id) if topic.parent_id else None
        if parent is not None and all(parent.id != t.id for t in themes):
            themes.append(parent)
    return [t.ref() for t in (*themes, *topics, *styles)]
