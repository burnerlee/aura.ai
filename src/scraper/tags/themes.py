# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Group fine-grained topic tags into a small set of coarse themes.

Topic tags are the right unit for matching and chips but far too numerous for an
Interest DNA ring (hundreds of tags, most seen once). Themes are the coarse level the
DNA is keyed by: spherical k-means over topic-tag embeddings, weighted by how many
posts carry each tag, labelled by the most common member.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, Field

from scraper.llm.base import LLMClient
from scraper.models.tag import Tag, TagKind
from scraper.tags.vocabulary import make_tag_id, normalize_label

logger = logging.getLogger(__name__)

MIN_THEMES = 6
MAX_THEMES = 24
# The LLM defines themes from the most common labels, then assigns the rest in chunks.
# Both stay small because the LLM clients cap output tokens.
MAX_PROMPT_TOPICS = 120
ASSIGN_CHUNK = 80


def default_theme_count(n_topics: int) -> int:
    """~sqrt(n) themes, clamped: 335 topic tags -> 18 themes."""
    return max(1, min(n_topics, max(MIN_THEMES, min(MAX_THEMES, round(math.sqrt(n_topics))))))


def _unit_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12, None)
    return mat / norms


def _kmeans(
    x: np.ndarray, w: np.ndarray, k: int, *, seed: int, max_iter: int = 40
) -> np.ndarray:
    """Weighted spherical k-means (cosine); returns each row's cluster index."""
    n = x.shape[0]
    rng = np.random.default_rng(seed)
    centers = np.empty((k, x.shape[1]), dtype=np.float32)
    centers[0] = x[int(np.argmax(w))]  # heaviest topic anchors the first theme
    for i in range(1, k):
        # Farthest-first, damped by weight: spread seeds over the embedding space.
        gap = 1.0 - np.max(x @ centers[:i].T, axis=1)
        probs = np.clip(gap, 0, None) * w
        total = float(probs.sum())
        pick = (
            int(rng.choice(n, p=probs / total)) if total > 1e-12 else int(rng.integers(0, n))
        )
        centers[i] = x[pick]
    assign = np.full(n, -1, dtype=np.int64)
    for _ in range(max_iter):
        new_assign = np.argmax(x @ centers.T, axis=1)
        if np.array_equal(new_assign, assign):
            break
        assign = new_assign
        for i in range(k):
            mask = assign == i
            if mask.any():
                centers[i] = _unit_rows((x[mask] * w[mask, None]).sum(axis=0, keepdims=True))[0]
    return assign


def _make_theme(
    label: str,
    group: Sequence[Tag],
    vectors: dict[str, np.ndarray],
    weights: dict[str, float],
) -> Tag | None:
    theme_id = make_tag_id(TagKind.THEME, label)
    if theme_id is None or not group:
        return None
    stack = np.stack([vectors[t.id] * weights[t.id] for t in group]).sum(axis=0, keepdims=True)
    centroid = _unit_rows(stack)[0]
    label_norm = normalize_label(label)
    aliases = sorted(
        {normalize_label(form) for tag in group for form in (tag.label, *tag.aliases)}
        - {label_norm}
    )
    return Tag(
        id=theme_id,
        kind=TagKind.THEME,
        label=label,
        aliases=aliases,
        doc_count=sum(t.doc_count for t in group),
        embedding=[float(v) for v in centroid],
    )


def _embedded_topics(topics: Sequence[Tag]) -> list[Tag]:
    return [t for t in topics if t.kind == TagKind.TOPIC and t.embedding]


def _vectors_and_weights(
    members: Sequence[Tag],
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    x = _unit_rows(np.asarray([t.embedding for t in members], dtype=np.float32))
    vectors = {t.id: x[i] for i, t in enumerate(members)}
    weights = {t.id: math.sqrt(max(1, t.doc_count)) for t in members}
    return vectors, weights


def build_themes(
    topics: Sequence[Tag],
    *,
    k: int | None = None,
    seed: int = 42,
) -> tuple[list[Tag], dict[str, str]]:
    """Embedding-only fallback: weighted k-means groups, labelled by the top member.

    Returns ``(themes, parent_of)`` where ``parent_of`` maps topic tag id -> theme id.
    A theme's aliases are every member label and alias, so any known label resolves to
    its theme by exact match. Proper nouns scatter in embedding space, so prefer
    ``themes_from_groups`` with LLM-made groups when an LLM is available.
    """
    members = _embedded_topics(topics)
    if not members:
        return [], {}
    vectors, weights = _vectors_and_weights(members)
    x = np.stack([vectors[t.id] for t in members])
    w = np.asarray([weights[t.id] for t in members], dtype=np.float32)
    clusters = _kmeans(x, w, k or default_theme_count(len(members)), seed=seed)

    groups: list[tuple[str, list[Tag]]] = []
    for idx in sorted(set(clusters.tolist())):
        group = [members[i] for i in np.flatnonzero(clusters == idx)]
        group.sort(key=lambda t: (-t.doc_count, len(t.label), t.label.lower()))
        groups.append((group[0].label, group))
    return themes_from_groups(members, groups)


def themes_from_groups(
    topics: Sequence[Tag],
    groups: Sequence[tuple[str, Sequence[Tag]]],
) -> tuple[list[Tag], dict[str, str]]:
    """Materialize themes from ``(label, member topic tags)`` groups.

    Any topic left out of every group attaches to the nearest theme by embedding, so
    every topic ends up with exactly one parent.
    """
    members = _embedded_topics(topics)
    if not members:
        return [], {}
    vectors, weights = _vectors_and_weights(members)

    built: list[tuple[Tag, list[Tag]]] = []
    assigned: dict[str, str] = {}
    used: set[str] = set()
    for label, group in groups:
        fresh = [t for t in group if t.id in vectors and t.id not in assigned]
        theme = _make_theme(label.strip(), fresh, vectors, weights)
        if theme is None or theme.id in used:
            continue
        used.add(theme.id)
        for tag in fresh:
            assigned[tag.id] = theme.id
        built.append((theme, fresh))
    if not built:
        return [], {}

    leftovers = [t for t in members if t.id not in assigned]
    if leftovers:
        centers = np.stack([np.asarray(theme.embedding, dtype=np.float32) for theme, _ in built])
        for tag in leftovers:
            best = int(np.argmax(centers @ vectors[tag.id]))
            built[best][1].append(tag)
            assigned[tag.id] = built[best][0].id
        # Rebuild so centroids / aliases / counts include the attached stragglers.
        rebuilt = [_make_theme(theme.label, group, vectors, weights) for theme, group in built]
        built = [(t, g) for t, (_, g) in zip(rebuilt, built, strict=True) if t is not None]
    return [theme for theme, _ in built], assigned


class _ThemeGroup(BaseModel):
    label: str
    topics: list[str] = Field(default_factory=list)


class _ThemePlan(BaseModel):
    themes: list[_ThemeGroup] = Field(default_factory=list)


class _Assignment(BaseModel):
    topic: str
    theme: str


class _AssignPlan(BaseModel):
    assignments: list[_Assignment] = Field(default_factory=list)


_PROMPT = """Group these topic labels from a reading-feed corpus into broad themes.

Rules:
- Produce between {lo} and {hi} themes. A theme is something a reader would say they are
  "into" in two or three words (e.g. "AI & machine learning", "Markets & investing",
  "Public health", "Pop culture"). Never use a person, brand or place name as a theme.
- Every topic label below must appear in exactly one theme, copied verbatim. A person,
  book, place or event belongs with the subject it is about.
- Prefer these existing theme names when they still fit: {preferred}
- Counts in parentheses are how many posts carry the label.

Return JSON: {{"themes": [{{"label": "...", "topics": ["...", "..."]}}]}}

Topic labels:
{labels}
"""

_ASSIGN_PROMPT = """Assign each topic label to the single best-fitting theme from this list.
A person, book, place or event belongs with the subject it is about. Use theme names
exactly as written.

Themes: {themes}

Return JSON: {{"assignments": [{{"topic": "...", "theme": "..."}}]}}

Topic labels:
{labels}
"""


def group_topics_with_llm(
    topics: Sequence[Tag],
    llm: LLMClient,
    preferred_labels: Sequence[str] = (),
) -> list[tuple[str, list[Tag]]] | None:
    """LLM-made theme groups; None if the answer is unusable (caller falls back).

    Pass 1 defines the themes from the most common labels. Pass 2 assigns the long tail
    to those themes in chunks. Anything the LLM skips is attached by embedding later.
    """
    members = sorted(_embedded_topics(topics), key=lambda t: (-t.doc_count, t.label.lower()))
    if len(members) < MIN_THEMES:
        return None
    head, tail = members[:MAX_PROMPT_TOPICS], members[MAX_PROMPT_TOPICS:]
    prompt = _PROMPT.format(
        lo=MIN_THEMES,
        hi=MAX_THEMES,
        preferred=", ".join(preferred_labels[:MAX_THEMES]) or "(none)",
        labels="\n".join(f"- {t.label} ({t.doc_count})" for t in head),
    )
    try:
        plan = llm.generate_json(prompt, _ThemePlan)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM theme grouping failed: %s", exc)
        return None

    by_norm = {normalize_label(t.label): t for t in members}
    groups: list[tuple[str, list[Tag]]] = []
    seen: set[str] = set()
    for item in plan.themes:
        found: list[Tag] = []
        for name in item.topics:
            tag = by_norm.get(normalize_label(name))
            if tag is not None and tag.id not in seen:
                seen.add(tag.id)
                found.append(tag)
        if item.label.strip() and found:
            groups.append((item.label.strip(), found))
    if not (3 <= len(groups) <= MAX_THEMES * 2):
        logger.warning("LLM theme grouping returned %d usable groups; ignoring", len(groups))
        return None

    theme_index = {normalize_label(label): i for i, (label, _) in enumerate(groups)}
    theme_names = ", ".join(label for label, _ in groups)
    for start in range(0, len(tail), ASSIGN_CHUNK):
        chunk = tail[start : start + ASSIGN_CHUNK]
        try:
            assigned = llm.generate_json(
                _ASSIGN_PROMPT.format(
                    themes=theme_names, labels="\n".join(f"- {t.label}" for t in chunk)
                ),
                _AssignPlan,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM theme assignment chunk failed (%s); using embeddings", exc)
            continue
        for item in assigned.assignments:
            tag = by_norm.get(normalize_label(item.topic))
            idx = theme_index.get(normalize_label(item.theme))
            if tag is not None and idx is not None and tag.id not in seen:
                seen.add(tag.id)
                groups[idx][1].append(tag)
    return groups
