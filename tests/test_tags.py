# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Canonical tag vocabulary: normalize, cluster, resolve, rebuild, apply."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from scraper.models.tag import Tag, TagKind
from scraper.tags.service import TagService
from scraper.tags.vocabulary import (
    LabelEntry,
    TagResolver,
    build_tags,
    collapse_labels,
    is_usable_label,
    make_tag_id,
    normalize_label,
    tag_refs_for_facets,
)

# Hand-placed 3D embeddings: AI-ish, space-ish, and cooking are well separated.
VECTORS: dict[str, list[float]] = {
    "AI": [1.0, 0.0, 0.0],
    "artificial intelligence": [0.99, 0.1, 0.0],
    "Space": [0.0, 1.0, 0.0],
    "astronomy": [0.0, 0.98, 0.2],
    "Cooking": [0.0, 0.0, 1.0],
    "deep dive": [0.5, 0.5, 0.7],
    "listicle": [-0.7, 0.3, -0.6],
}


def _embed(text: str) -> list[float]:
    return VECTORS[text]


def test_normalize_label_collapses_case_and_punctuation():
    assert normalize_label("  A.I. ") == "a i"
    assert normalize_label("Machine-Learning") == "machine learning"
    assert normalize_label("R&D") == "r and d"
    assert make_tag_id(TagKind.TOPIC, "Practical AI") == "topic:practical-ai"
    assert make_tag_id(TagKind.TOPIC, "!!!") is None


def test_generic_and_oversized_labels_are_not_usable():
    assert not is_usable_label("Newsletter")
    assert not is_usable_label("")
    assert not is_usable_label("x" * 80)
    assert is_usable_label("Deep space")


def test_collapse_labels_merges_case_variants_and_picks_display():
    merged = {c.normalized: c for c in collapse_labels({"AI": 5, "ai": 3, "Space": 2})}
    assert merged["ai"].count == 8
    assert merged["ai"].label == "AI"
    assert merged["space"].count == 2


def _entries() -> list[LabelEntry]:
    return [
        LabelEntry("artificial intelligence", 2, VECTORS["artificial intelligence"]),
        LabelEntry("AI", 8, VECTORS["AI"]),
        LabelEntry("Space", 4, VECTORS["Space"]),
        LabelEntry("astronomy", 1, VECTORS["astronomy"]),
        LabelEntry("Cooking", 2, VECTORS["Cooking"]),
    ]


def test_build_tags_clusters_by_cosine_and_counts_docs():
    tags = {t.id: t for t in build_tags(TagKind.TOPIC, _entries(), threshold=0.85)}
    assert set(tags) == {"topic:ai", "topic:space", "topic:cooking"}
    assert tags["topic:ai"].aliases == ["artificial intelligence"]
    assert tags["topic:ai"].doc_count == 10
    assert tags["topic:space"].aliases == ["astronomy"]
    assert tags["topic:cooking"].aliases == []


def test_build_tags_threshold_controls_merging():
    strict = build_tags(TagKind.TOPIC, _entries(), threshold=0.999)
    assert len(strict) == 5


def test_build_tags_keeps_existing_canonical_label_stable():
    entries = [
        LabelEntry("Artificial Intelligence", 50, VECTORS["artificial intelligence"]),
        LabelEntry("AI", 3, VECTORS["AI"]),
    ]
    fresh = build_tags(TagKind.TOPIC, entries, threshold=0.85)
    assert [t.id for t in fresh] == ["topic:artificial-intelligence"]

    sticky = build_tags(TagKind.TOPIC, entries, threshold=0.85, preferred={"ai"})
    assert [t.id for t in sticky] == ["topic:ai"]
    assert sticky[0].aliases == ["artificial intelligence"]


def _vocab() -> list[Tag]:
    return build_tags(TagKind.TOPIC, _entries(), threshold=0.85) + build_tags(
        TagKind.STYLE,
        [LabelEntry("deep dive", 3, VECTORS["deep dive"])],
        threshold=0.85,
    )


def test_resolver_exact_alias_needs_no_embedding():
    resolver = TagResolver(_vocab())
    assert resolver.resolve("Artificial  Intelligence").id == "topic:ai"
    assert resolver.resolve("ASTRONOMY").id == "topic:space"
    assert resolver.resolve("unknown thing") is None
    assert resolver.resolve("newsletter") is None


def test_resolver_falls_back_to_nearest_tag_by_embedding():
    VECTORS["ml"] = [0.97, 0.2, 0.0]
    VECTORS["baking"] = [0.1, 0.1, 0.95]
    VECTORS["opera"] = [-0.5, -0.5, 0.1]
    resolver = TagResolver(_vocab(), embed_fn=_embed, threshold=0.85)
    assert resolver.resolve("ml").id == "topic:ai"
    assert resolver.resolve("baking").id == "topic:cooking"
    assert resolver.resolve("opera") is None


def test_resolver_does_not_cross_kinds():
    resolver = TagResolver(_vocab())
    assert resolver.resolve("deep dive", TagKind.TOPIC) is None
    assert resolver.resolve("deep dive", TagKind.STYLE).id == "style:deep-dive"


def test_resolver_follows_merged_into():
    ai = Tag(id="topic:ai", kind=TagKind.TOPIC, label="AI")
    old = Tag(id="topic:ml", kind=TagKind.TOPIC, label="ML", merged_into="topic:ai")
    resolver = TagResolver([ai, old])
    assert resolver.by_id("topic:ml").id == "topic:ai"
    assert resolver.by_id("topic:missing") is None
    # Retired tags are not resolution targets for new labels.
    assert resolver.resolve("ML") is None


def test_tag_refs_for_facets_orders_topics_then_styles():
    resolver = TagResolver(_vocab())
    refs = tag_refs_for_facets(
        {"topics": ["astronomy", "AI", "nonsense"], "style": ["Deep dive"]}, resolver
    )
    assert [r.id for r in refs] == ["topic:space", "topic:ai", "style:deep-dive"]
    assert tag_refs_for_facets(None, resolver) == []


class FakeStore:
    """In-memory stand-in for the Mongo calls TagService makes."""

    def __init__(self, posts: list[dict[str, Any]]) -> None:
        self.posts = posts
        self.tags: dict[str, Tag] = {}
        self.post_tags: dict[Any, list[dict[str, Any]]] = {}

    def facet_label_counts(self, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for post in self.posts:
            for label in post["facets"].get(field, []):
                counts[label] = counts.get(label, 0) + 1
        return counts

    def list_tags(self, *, kind=None, min_docs=0, include_merged=True, limit=None):
        out = [
            t
            for t in self.tags.values()
            if (kind is None or t.kind == kind)
            and t.doc_count >= min_docs
            and (include_merged or t.merged_into is None)
        ]
        out.sort(key=lambda t: -t.doc_count)
        return out[:limit] if limit else out

    def save_tags(self, tags: list[Tag]) -> int:
        for tag in tags:
            self.tags[tag.id] = tag
        return len(tags)

    def iter_for_tagging(self, *, source=None, limit=None):
        yield from self.posts

    def set_post_tags(self, updates) -> int:
        for post_id, refs in updates:
            self.post_tags[post_id] = refs
        return len(updates)

    def tag_doc_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for refs in self.post_tags.values():
            for ref in refs:
                counts[ref["id"]] = counts.get(ref["id"], 0) + 1
        return counts

    def set_tag_doc_counts(self, counts: dict[str, int]) -> None:
        for tag in self.tags.values():
            tag.doc_count = counts.get(tag.id, 0)


def _post(post_id: str, topics: list[str], style: list[str] | None = None) -> dict[str, Any]:
    return {
        "_id": post_id,
        "source": "substack",
        "external_id": post_id,
        "facets": {"topics": topics, "style": style or []},
    }


def _service(posts: list[dict[str, Any]]) -> tuple[TagService, FakeStore, MagicMock]:
    store = FakeStore(posts)
    client = MagicMock()
    client.embed_query.side_effect = _embed
    vectors = MagicMock()
    service = TagService(store=store, vectors=vectors, client=client)  # type: ignore[arg-type]
    return service, store, vectors


def test_rebuild_builds_vocabulary_tags_posts_and_recounts():
    posts = [
        _post("p1", ["AI", "newsletter"], ["deep dive"]),
        _post("p2", ["artificial intelligence"]),
        _post("p3", ["astronomy", "Space"]),
        _post("p4", ["Cooking"], ["listicle"]),
        _post("p5", ["Space"]),
    ]
    service, store, vectors = _service(posts)

    summary = service.rebuild()

    topic_style = {tid for tid in store.tags if not tid.startswith("theme:")}
    assert topic_style == {
        "topic:ai",
        "topic:space",
        "topic:cooking",
        "style:deep-dive",
        "style:listicle",
    }
    # Too few topics for the LLM, so themes fall back to embedding clusters (one each).
    assert {tid for tid in store.tags if tid.startswith("theme:")} == {
        "theme:ai",
        "theme:space",
        "theme:cooking",
    }
    assert store.tags["topic:ai"].parent_id == "theme:ai"
    assert store.tags["topic:ai"].aliases == ["artificial intelligence"]
    assert summary["apply"]["tagged"] == 5
    # Themes first (the post's primary theme), then topics, then styles.
    assert [r["id"] for r in store.post_tags["p1"]] == [
        "theme:ai",
        "topic:ai",
        "style:deep-dive",
    ]
    assert [r["id"] for r in store.post_tags["p3"]] == ["theme:space", "topic:space"]
    # doc_count is posts carrying the tag, not raw label occurrences.
    assert store.tags["topic:ai"].doc_count == 2
    assert store.tags["topic:space"].doc_count == 2
    vectors.set_payload.assert_any_call("substack", "p2", {"tag_ids": ["theme:ai", "topic:ai"]})


def test_rebuild_dry_run_writes_nothing():
    service, store, vectors = _service(
        [_post("p1", ["AI"]), _post("p2", ["artificial intelligence"])]
    )
    summary = service.rebuild(dry_run=True)
    assert store.tags == {}
    assert store.post_tags == {}
    assert summary["clusters"][0]["id"] == "topic:ai"
    vectors.set_payload.assert_not_called()


def test_rebuild_reuses_stored_embeddings_for_known_labels():
    service, store, _ = _service([_post("p1", ["AI"]), _post("p2", ["Space"])])
    service.rebuild()
    service.client.embed_query.reset_mock()
    service.rebuild()
    service.client.embed_query.assert_not_called()


def test_retire_links_vanished_tag_to_its_replacement():
    old = Tag(id="topic:ml", kind=TagKind.TOPIC, label="ML", doc_count=4)
    keep = Tag(id="topic:ai", kind=TagKind.TOPIC, label="AI", doc_count=9)
    new_ai = Tag(id="topic:ai", kind=TagKind.TOPIC, label="AI", aliases=["ml"], doc_count=12)
    stale = TagService._retire({"topic:ml": old, "topic:ai": keep}, [new_ai])
    assert [t.id for t in stale] == ["topic:ml"]
    assert stale[0].merged_into == "topic:ai"
    assert stale[0].doc_count == 0


def test_top_labels_and_public_listing_hide_embeddings_and_merged():
    service, store, _ = _service(
        [_post("p1", ["AI"]), _post("p2", ["Space"]), _post("p3", ["Space"])]
    )
    service.rebuild()
    assert service.top_labels(limit=5) == ["Space", "AI"]
    public = service.list_public(kind=TagKind.TOPIC)
    assert public[0]["id"] == "topic:space"
    assert "embedding" not in public[0]
