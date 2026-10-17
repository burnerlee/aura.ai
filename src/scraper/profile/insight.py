# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Explain a recommendation in plain language, using only facts we actually hold.

The match chip says *how well* a post fits; this says *why*, with evidence the user
can check: how much of their Interest DNA the post's theme is, which posts they liked
(or skipped) it resembles, which topics they have engaged with, and which learned
patterns apply. Posts are only cited when the evidence is corroborated; a bare
embedding cosine is not trusted on its own because unrelated posts score 0.74-0.82.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from scraper.models.user import InterestDNA
from scraper.query.types import (
    InsightPostRef,
    InsightReason,
    MatchInsight,
    ScoredPost,
)

# Close enough to cite on similarity alone (near-duplicates, series, same author voice).
STRONG_SIMILARITY = 0.85
# Close enough to cite only when the posts also share a fine-grained topic tag.
CORROBORATED_SIMILARITY = 0.74
LIKED_REFS = 2
SKIPPED_REFS = 1
VARIETY_BELOW_PERCENT = 50
FRESH_HOURS = 48
_TITLE_CHARS = 58
_BIG_THEMES = 3


@dataclass(frozen=True)
class UserPost:
    """A post the user reacted to, reduced to what comparison needs."""

    post_id: str
    title: str
    vector: np.ndarray  # unit length
    topic_ids: frozenset[str] = field(default_factory=frozenset)


def unit(vector: Sequence[float]) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 1e-12 else arr


def _quote(title: str) -> str:
    clean = " ".join(title.split())
    if len(clean) > _TITLE_CHARS:
        clean = clean[: _TITLE_CHARS - 1].rstrip() + "…"
    return f"“{clean}”"


def _join(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _ago(hours: float) -> str:
    if hours < 1:
        return "less than an hour"
    if hours < 48:
        return f"{round(hours)} hour{'s' if round(hours) != 1 else ''}"
    return f"{round(hours / 24)} days"


def _topic_ids(tag_ids: Iterable[str]) -> frozenset[str]:
    return frozenset(t for t in tag_ids if t.startswith("topic:"))


def _nearest(
    vector: np.ndarray,
    topics: frozenset[str],
    candidates: Sequence[UserPost],
    label: Callable[[str], str],
    limit: int,
) -> list[tuple[UserPost, float, list[str]]]:
    """Reacted-to posts this one demonstrably resembles, best first."""
    found: list[tuple[UserPost, float, list[str]]] = []
    for other in candidates:
        sim = float(vector @ other.vector)
        shared = sorted(topics & other.topic_ids)
        if sim >= STRONG_SIMILARITY or (sim >= CORROBORATED_SIMILARITY and shared):
            found.append((other, sim, [label(t) for t in shared]))
    found.sort(key=lambda item: -(item[1] + 0.05 * len(item[2])))
    return found[:limit]


def _attribution_text(
    attribution: str | None,
    dna: InterestDNA,
    label: Callable[[str], str],
    in_dna: str | None,
) -> str | None:
    """User-facing phrasing for the query that pulled a post in; never internal labels.

    Query vectors are named ``state`` / ``persona`` / ``interest_N`` internally, which
    mean nothing to a reader, so those are translated (or dropped).
    """
    if not attribution:
        return None
    if attribution == "state":
        return "It lines up with the overall pattern in the posts you have liked."
    if attribution == "persona":
        return "It matches the profile you described to Aura."
    theme_labels = {label(key) for key in dna.weights}
    if attribution in theme_labels and (in_dna is None or label(in_dna) != attribution):
        return f"It was pulled in by your {attribution} interest."
    return None


def build_insight(
    post: ScoredPost,
    *,
    dna: InterestDNA,
    liked: Sequence[UserPost],
    skipped: Sequence[UserPost],
    label: Callable[[str], str],
    now: float | None = None,
) -> MatchInsight | None:
    """Plain-language account of why ``post`` is in this user's feed."""
    match = post.match
    if match is None:
        return None
    payload = post.payload
    tag_ids: list[str] = list(payload.get("tag_ids") or [])
    topics = _topic_ids(tag_ids)
    reasons: list[InsightReason] = []
    refs: list[InsightPostRef] = []

    def add(kind: str, text: str) -> None:
        reasons.append(InsightReason(kind=kind, text=text))  # type: ignore[arg-type]

    if match.percent is None:
        headline = "Too few posts were scored to rank this one yet"
    else:
        top = max(1, 100 - match.percent)
        headline = f"Top {top}% of the {match.pool_size} posts we considered for you"

    # --- where it sits in the Interest DNA ----------------------------------------
    ranked = sorted(dna.weights.items(), key=lambda kv: -kv[1])
    rank_of = {key: i for i, (key, _) in enumerate(ranked, start=1)}
    theme_ids = [t for t in tag_ids if t.startswith("theme:")]
    primary = theme_ids[0] if theme_ids else None  # what the card's category chip shows
    # A post can carry several themes; the one the user cares about most is the one that
    # explains why it is here, even when it is filed under another.
    in_dna = min((t for t in tag_ids if t in rank_of), key=rank_of.get, default=None)
    in_top_theme = in_dna is not None and rank_of[in_dna] <= _BIG_THEMES
    if in_dna is not None:
        share, rank = dna.weights[in_dna], rank_of[in_dna]
        place = (
            ", your biggest theme"
            if rank == 1
            else f", your number {rank} theme"
            if rank <= _BIG_THEMES
            else ""
        )
        lead = (
            f"It is filed under {label(primary)} but also touches {label(in_dna)}"
            if primary and primary != in_dna
            else f"It sits in {label(in_dna)}"
        )
        add("theme", f"{lead}, {share:.0f}% of your Interest DNA{place}.")
    elif primary:
        add("theme", f"{label(primary)} is not part of your Interest DNA yet.")

    # --- evidence from posts the user reacted to ---------------------------------------
    vector = unit(post.doc_vector) if post.doc_vector else None
    similar_liked = _nearest(vector, topics, liked, label, LIKED_REFS) if vector is not None else []
    similar_skipped = (
        _nearest(vector, topics, skipped, label, SKIPPED_REFS) if vector is not None else []
    )
    for other, sim, shared in similar_liked:
        refs.append(
            InsightPostRef(
                post_id=other.post_id,
                title=other.title,
                relation="liked",
                similarity=round(sim, 3),
                shared_topics=shared,
            )
        )
    overlap: dict[str, int] = {}
    for other in liked:
        for t in topics & other.topic_ids:
            overlap[t] = overlap.get(t, 0) + 1
    if similar_liked:
        quoted = _join([_quote(o.title) for o, _, _ in similar_liked])
        shared_all = sorted({t for _, _, s_ in similar_liked for t in s_})
        if similar_liked[0][1] >= STRONG_SIMILARITY:
            extra = f" (both about {_join(shared_all[:2])})" if shared_all else ""
            add("similar_liked", f"It reads a lot like {quoted}, which you resonated with{extra}.")
        else:
            # Similar enough to compare only because the tags agree, so say what agrees.
            add(
                "similar_liked",
                f"It shares {_join(shared_all[:3])} with {quoted}, which you resonated with.",
            )
    elif overlap:
        best = sorted(overlap.items(), key=lambda kv: -kv[1])[:2]
        n = max(c for _, c in best)
        add(
            "shared_topics",
            f"It covers {_join([label(t) for t, _ in best])}, which "
            f"{'appears' if n == 1 else 'appear'} in {n} post{'s' if n != 1 else ''} you liked.",
        )
    else:
        # No specific past reaction to point at, so describe which signal pulled it in.
        pulled = _attribution_text(match.top_attribution, dna, label, in_dna)
        if pulled:
            add("attribution", pulled)

    # --- patterns we learned about this user ------------------------------------------
    likes = [f.label for f in match.flags if f.kind == "affinity"]
    avoids = [f.label for f in match.flags if f.kind == "aversion"]
    if likes:
        add("affinity", f"You tend to like {_join(likes)} posts, and this is one.")
    if avoids:
        add(
            "caution",
            f"Heads up: it is {_join(avoids)}, which you have been skipping, so it may miss.",
        )
    for other, sim, shared in similar_skipped:
        refs.append(
            InsightPostRef(
                post_id=other.post_id,
                title=other.title,
                relation="skipped",
                similarity=round(sim, 3),
                shared_topics=shared,
            )
        )
        if sim >= STRONG_SIMILARITY:
            add("similar_skipped", f"It is also close to {_quote(other.title)}, which you skipped.")
        else:
            # Only corroborated by tags, so name what agrees rather than claiming closeness.
            add(
                "similar_skipped",
                f"It shares {_join(shared[:3])} with {_quote(other.title)}, which you skipped.",
            )

    # --- freshness, then an honest note for stretches and first-timers ---------------
    published = payload.get("published_at")
    if isinstance(published, (int, float)):
        hours = ((now if now is not None else time.time()) - published) / 3600.0
        if 0 <= hours <= FRESH_HOURS:
            add("fresh", f"It was published {_ago(hours)} ago.")

    if not liked and not skipped:
        add(
            "cold_start",
            "You have not reacted to any posts yet, so this is based only on the interests "
            "you told Aura about. Resonate or banish a few and it will sharpen.",
        )
    elif (match.percent is not None and match.percent < VARIETY_BELOW_PERCENT) or not in_top_theme:
        add(
            "variety",
            "It is more of a stretch from your usual themes, so think of it as a variety "
            "pick. How you react tells Aura whether to bring more like it.",
        )

    return MatchInsight(
        headline=headline,
        summary=" ".join([f"{headline}."] + [r.text for r in reasons]),
        reasons=reasons,
        references=refs,
    )
