# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Match insight: a readable account of why a post is in the feed, built only from facts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from scraper.api.cards import hydrate_scored
from scraper.models.user import InterestDNA, UserProfile
from scraper.profile.insight import (
    CORROBORATED_SIMILARITY,
    STRONG_SIMILARITY,
    UserPost,
    build_insight,
    unit,
)
from scraper.profile.service import UserProfileService
from scraper.query.types import MatchFlag, MatchInfo, ScoredPost
from scraper.storage.qdrant import point_id_for

NOW = 1_800_000_000.0
LABELS = {
    "theme:ai": "AI & machine learning",
    "theme:markets": "Markets & investing",
    "theme:health": "Health & medicine",
    "theme:policy": "Policy & politics",
    "topic:llms": "Large Language Models",
    "topic:ml": "Machine Learning",
    "topic:stocks": "Stock Market",
}


def label(tag_id: str) -> str:
    return LABELS.get(tag_id, tag_id)


def vec_at(cosine: float) -> list[float]:
    """A unit vector whose cosine with [1, 0] is ``cosine``."""
    return [cosine, float(np.sqrt(max(0.0, 1 - cosine**2)))]


BASE = unit([1.0, 0.0])


def user_post(pid: str, title: str, cosine: float, topics: tuple[str, ...] = ()) -> UserPost:
    return UserPost(
        post_id=pid, title=title, vector=unit(vec_at(cosine)), topic_ids=frozenset(topics)
    )


def scored(
    *,
    tags: tuple[str, ...] = ("theme:ai", "topic:llms"),
    percent: int | None = 90,
    attribution: str | None = None,
    flags: tuple[MatchFlag, ...] = (),
    published_hours_ago: float | None = None,
    pool: int = 64,
) -> ScoredPost:
    payload: dict = {"title": "Candidate", "tag_ids": list(tags)}
    if published_hours_ago is not None:
        payload["published_at"] = NOW - published_hours_ago * 3600
    return ScoredPost(
        post_id="cand",
        score=0.7,
        payload=payload,
        doc_vector=[float(x) for x in BASE],
        match=MatchInfo(
            percent=percent,
            fit=0.7,
            pool_size=pool,
            top_attribution=attribution,
            flags=list(flags),
        ),
    )


DNA = InterestDNA(
    weights={"theme:ai": 50.0, "theme:markets": 30.0, "theme:health": 12.0, "theme:policy": 8.0},
    version=3,
)


def insight(post: ScoredPost, *, liked=(), skipped=(), dna: InterestDNA = DNA):
    result = build_insight(post, dna=dna, liked=liked, skipped=skipped, label=label, now=NOW)
    assert result is not None
    return result


def kinds(result) -> list[str]:
    return [r.kind for r in result.reasons]


def text_of(result, kind: str) -> str:
    return next(r.text for r in result.reasons if r.kind == kind)


def test_no_match_means_no_insight():
    post = scored()
    post.match = None
    assert build_insight(post, dna=DNA, liked=[], skipped=[], label=label) is None


def test_headline_is_relative_and_never_claims_top_zero():
    assert insight(scored(percent=95)).headline == "Top 5% of the 64 posts we considered for you"
    assert insight(scored(percent=98, pool=70)).headline.startswith("Top 2% of the 70")
    assert insight(scored(percent=100)).headline.startswith("Top 1%")
    assert "Too few posts" in insight(scored(percent=None)).headline


def test_theme_reason_states_share_and_rank():
    liked = [user_post("l", "x", 0.2)]
    assert "50% of your Interest DNA, your biggest theme" in text_of(
        insight(scored(), liked=liked), "theme"
    )
    second = insight(scored(tags=("theme:markets",)), liked=liked)
    assert "30% of your Interest DNA, your number 2 theme" in text_of(second, "theme")
    third = insight(scored(tags=("theme:health",)), liked=liked)
    assert "12% of your Interest DNA, your number 3 theme" in text_of(third, "theme")
    fourth = insight(scored(tags=("theme:policy",)), liked=liked)
    assert "8% of your Interest DNA" in text_of(fourth, "theme")
    assert "number" not in text_of(fourth, "theme")


def test_a_post_filed_under_one_theme_but_touching_another_says_so():
    text = text_of(insight(scored(tags=("theme:markets", "theme:ai", "topic:llms"))), "theme")
    # Chip says Markets; the DNA theme that explains it is AI, the user's biggest.
    assert "filed under Markets & investing but also touches AI & machine learning" in text
    assert "50%" in text


def test_theme_missing_from_the_dna_is_stated_plainly():
    post = scored(tags=("theme:unknown",))
    assert "theme:unknown is not part of your Interest DNA yet" in text_of(insight(post), "theme")


def test_strong_similarity_is_cited_as_reads_like_and_recorded_as_a_reference():
    liked = [user_post("l1", "Why GPUs got cheaper", STRONG_SIMILARITY + 0.05, ("topic:llms",))]
    result = insight(scored(), liked=liked)
    text = text_of(result, "similar_liked")
    assert "reads a lot like “Why GPUs got cheaper”, which you resonated with" in text
    assert "both about Large Language Models" in text
    ref = result.references[0]
    assert (ref.post_id, ref.relation) == ("l1", "liked")
    assert ref.shared_topics == ["Large Language Models"]


def test_moderate_similarity_needs_a_shared_topic_and_is_worded_honestly():
    shared = [user_post("l1", "On tokenizers", 0.78, ("topic:llms", "topic:ml"))]
    text = text_of(
        insight(scored(tags=("theme:ai", "topic:llms", "topic:ml")), liked=shared), "similar_liked"
    )
    # Not "is close to": similarity alone is not trusted, the agreement is in the tags.
    assert "shares Large Language Models and Machine Learning with “On tokenizers”" in text


def test_moderate_similarity_without_a_shared_topic_is_not_cited():
    """Unrelated posts routinely score 0.74-0.82, so a bare cosine proves nothing."""
    stranger = [user_post("l1", "A recipe for sourdough", 0.80, ("topic:other",))]
    result = insight(scored(), liked=stranger)
    assert result.references == []
    assert "similar_liked" not in kinds(result)
    assert "sourdough" not in result.summary


def test_below_the_floor_is_never_cited_even_with_a_shared_topic():
    far = [user_post("l1", "Barely related", CORROBORATED_SIMILARITY - 0.05, ("topic:llms",))]
    assert insight(scored(), liked=far).references == []


def test_at_most_two_liked_posts_are_cited_best_first():
    liked = [
        user_post("a", "Third best", 0.86),
        user_post("b", "Best", 0.97),
        user_post("c", "Second best", 0.91),
        user_post("d", "Fourth", 0.855),
    ]
    refs = insight(scored(), liked=liked).references
    assert [r.post_id for r in refs] == ["b", "c"]


def test_overlapping_topics_are_reported_when_no_single_post_is_close_enough():
    liked = [
        user_post("l1", "Far one", 0.30, ("topic:llms",)),
        user_post("l2", "Far two", 0.20, ("topic:llms", "topic:ml")),
    ]
    result = insight(scored(tags=("theme:ai", "topic:llms", "topic:ml")), liked=liked)
    assert result.references == []
    assert "It covers Large Language Models and Machine Learning" in text_of(
        result, "shared_topics"
    )
    assert "appear in 2 posts you liked" in text_of(result, "shared_topics")


def test_a_close_skipped_post_is_a_caution_not_a_recommendation():
    skipped = [user_post("s1", "Hot take on rates", 0.92, ("topic:stocks",))]
    result = insight(
        scored(tags=("theme:markets", "topic:stocks")),
        liked=[user_post("l", "z", 0.1)],
        skipped=skipped,
    )
    text = text_of(result, "similar_skipped")
    assert "It is also close to “Hot take on rates”, which you skipped" in text
    assert [(r.relation, r.post_id) for r in result.references] == [("skipped", "s1")]


def test_a_skipped_post_matched_only_by_a_shared_topic_does_not_claim_closeness():
    skipped = [user_post("s1", "Hot take on rates", 0.78, ("topic:stocks",))]
    result = insight(
        scored(tags=("theme:markets", "topic:stocks")),
        liked=[user_post("l", "z", 0.1)],
        skipped=skipped,
    )
    text = text_of(result, "similar_skipped")
    assert "shares Stock Market with “Hot take on rates”, which you skipped" in text
    assert "close to" not in text


def test_learned_patterns_become_a_plus_and_a_heads_up():
    flags = (
        MatchFlag(kind="affinity", label="technical", rule_key="style:technical"),
        MatchFlag(kind="aversion", label="long reads", rule_key="length:long"),
    )
    result = insight(scored(flags=flags), liked=[user_post("l", "z", 0.1)])
    assert "You tend to like technical posts, and this is one." in text_of(result, "affinity")
    assert "Heads up: it is long reads, which you have been skipping" in text_of(result, "caution")


def test_with_no_evidence_it_explains_which_signal_pulled_it_in_without_internal_names():
    liked = [user_post("l", "z", 0.1)]
    assert "overall pattern in the posts you have liked" in text_of(
        insight(scored(attribution="state"), liked=liked), "attribution"
    )
    assert "profile you described to Aura" in text_of(
        insight(scored(attribution="persona"), liked=liked), "attribution"
    )
    # A theme the user holds, different from the post's own: worth saying.
    pulled = insight(
        scored(tags=("theme:health",), attribution="AI & machine learning"), liked=liked
    )
    assert "pulled in by your AI & machine learning interest" in text_of(pulled, "attribution")


@pytest.mark.parametrize("internal", ["interest_0", "interest_3", "centroid", "content", "seed"])
def test_internal_query_labels_never_reach_the_reader(internal):
    result = insight(scored(attribution=internal), liked=[user_post("l", "z", 0.1)])
    assert "attribution" not in kinds(result)
    assert internal not in result.summary


def test_an_attribution_already_explained_by_the_theme_is_not_repeated():
    result = insight(scored(attribution="AI & machine learning"), liked=[user_post("l", "z", 0.1)])
    assert "attribution" not in kinds(result)


def test_cold_start_is_honest_about_having_only_stated_interests():
    result = insight(scored())
    assert "cold_start" in kinds(result)
    assert "have not reacted to any posts yet" in text_of(result, "cold_start")
    assert "variety" not in kinds(result)


def test_a_stretch_outside_the_top_themes_is_framed_as_variety():
    liked = [user_post("l", "z", 0.1)]
    off_theme = insight(scored(tags=("theme:policy",), percent=80), liked=liked)
    assert "variety pick" in text_of(off_theme, "variety")
    weak = insight(scored(percent=30), liked=liked)  # in the top theme but a weak fit
    assert "variety" in kinds(weak)
    strong = insight(scored(percent=90), liked=liked)
    assert "variety" not in kinds(strong)


def test_freshness_only_when_recent():
    liked = [user_post("l", "z", 0.1)]
    assert "published 5 hours ago" in text_of(
        insight(scored(published_hours_ago=5), liked=liked), "fresh"
    )
    assert "published 1 hour ago" in text_of(
        insight(scored(published_hours_ago=1.2), liked=liked), "fresh"
    )
    assert "fresh" not in kinds(insight(scored(published_hours_ago=200), liked=liked))
    assert "fresh" not in kinds(insight(scored(), liked=liked))


def test_long_titles_are_truncated_and_the_summary_stitches_every_reason():
    liked = [user_post("l", "A very long title " * 8, 0.95)]
    result = insight(scored(published_hours_ago=2), liked=liked)
    quoted = text_of(result, "similar_liked")
    assert "…”" in quoted and len(quoted) < 200
    assert result.summary.startswith(result.headline + ".")
    for reason in result.reasons:
        assert reason.text in result.summary


# --- service: gathers the user's reactions in batched lookups -----------------------------


def _service(docs: dict[str, dict], vectors: dict[str, list[float]]) -> UserProfileService:
    store = MagicMock()
    store.get_many_by_ids.side_effect = lambda ids: {i: docs[i] for i in ids if i in docs}
    qdrant = MagicMock()
    qdrant.fetch.side_effect = lambda ids, with_vectors=False: [
        SimpleNamespace(id=pid, vector={"doc": vectors[pid]}) for pid in ids if pid in vectors
    ]
    tags = MagicMock()
    tags.resolver.return_value = None  # labels fall back to humanized ids
    return UserProfileService(
        store=store,
        vectors=qdrant,
        engine=MagicMock(),
        client=MagicMock(),
        inference_client=MagicMock(),
        tag_service=tags,
    )


def _doc(pid: str, title: str, tags: list[str]) -> dict:
    return {
        "_id": pid,
        "source": "substack",
        "external_id": f"e-{pid}",
        "title": title,
        "tag_ids": tags,
    }


def test_service_attaches_insights_citing_real_reactions_with_batched_lookups():
    docs = {
        "L1": _doc("L1", "A post I liked", ["theme:ai", "topic:llms"]),
        "S1": _doc("S1", "A post I skipped", ["theme:markets", "topic:stocks"]),
    }
    vectors = {
        point_id_for("substack", "e-L1"): vec_at(0.97),
        point_id_for("substack", "e-S1"): vec_at(0.2),
    }
    service = _service(docs, vectors)
    profile = UserProfile(user_id="u", positive_ids=["L1"], negative_ids=["S1"], dna=DNA)
    results = [scored(), scored(tags=("theme:markets",), percent=20)]

    service._attach_insights(profile, results)

    first = results[0].insight
    assert first is not None
    assert [r.post_id for r in first.references] == ["L1"]
    assert "A post I liked" in first.summary
    assert results[1].insight is not None
    # One Mongo lookup and one Qdrant lookup per list, independent of how many cards.
    assert service.store.get_many_by_ids.call_count == 2
    assert service.vectors.fetch.call_count == 2


def test_service_skips_reactions_that_have_no_title_or_vector():
    docs = {"L1": _doc("L1", "", ["theme:ai"]), "L2": _doc("L2", "Has title", ["theme:ai"])}
    vectors = {point_id_for("substack", "e-L2"): vec_at(0.97)}  # L1 has no vector either
    service = _service(docs, vectors)
    profile = UserProfile(user_id="u", positive_ids=["L1", "L2"], dna=DNA)
    result = scored()
    service._attach_insights(profile, [result])
    assert [r.post_id for r in result.insight.references] == ["L2"]


def test_insight_travels_on_the_feed_card():
    post = scored()
    post.insight = insight(post, liked=[user_post("l", "Liked one", 0.95)])
    cards = hydrate_scored([post], {})
    assert cards[0].insight is not None
    assert cards[0].insight.references[0].title == "Liked one"
    # The embedding is internal and must never be serialized to clients.
    assert "doc_vector" not in post.model_dump()
