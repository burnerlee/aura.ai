# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Learning from feedback: snapshots, pattern mining, and the server-side DNA loop."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from scraper.models.tag import Tag, TagKind
from scraper.models.user import (
    DNAPatch,
    DNARule,
    DNARuleKind,
    DNARuleSource,
    EventType,
    Interaction,
    InterestDNA,
)
from scraper.profile.dna import adjust_weight
from scraper.profile.patterns import (
    Attr,
    Observation,
    attributes,
    build_snapshot,
    merge_mined,
    mine_rules,
    noticed_for,
    observations_from_interactions,
)
from scraper.profile.service import UserProfileService
from scraper.tags.vocabulary import TagResolver

# ---------------------------------------------------------------- snapshots / attributes


def _post(post_id: str, *, style: str = "analytical", words: int = 800, **extra: Any) -> dict:
    return {
        "_id": post_id,
        "external_id": f"ext-{post_id}",
        "source": "substack",
        "author": {"name": f"author-{post_id}"},
        "word_count": words,
        "facets": {
            "topics": ["LLMs"],
            "emotion": {"excitement": 0.7, "awe": 0.2},
            "reading_level": "advanced",
        },
        "canonical_tags": [
            {"id": "theme:ai", "label": "AI", "kind": "theme"},
            {"id": "topic:llms", "label": "LLMs", "kind": "topic"},
            {"id": f"style:{style}", "label": style, "kind": "style"},
        ],
        **extra,
    }


def test_snapshot_captures_post_attributes_and_the_card_context():
    snap = build_snapshot(
        _post("p1", style="listicle"),
        theme=("theme:ai", "AI"),
        matched_label="Markets",
        match_percent=91,
    )
    assert snap["theme_id"] == "theme:ai"
    assert snap["emotion"] == "excitement"
    assert snap["matched_label"] == "Markets" and snap["match_percent"] == 91
    assert snap["author"] == "author-p1" and snap["source"] == "substack"
    assert {t["kind"] for t in snap["tags"]} == {"theme", "topic", "style"}


def test_attributes_exclude_the_theme_and_bucket_the_length():
    snap = build_snapshot(
        _post("p1", words=1600), theme=None, matched_label=None, match_percent=None
    )
    attrs = attributes(snap)
    kinds = {(a.kind, a.key) for a in attrs}
    assert (DNARuleKind.STYLE, "style:analytical") in kinds
    assert (DNARuleKind.TOPIC, "topic:llms") in kinds
    assert (DNARuleKind.LENGTH, "long") in kinds
    assert (DNARuleKind.EMOTION, "excitement") in kinds
    assert not any(a.key == "theme:ai" for a in attrs)  # theme taste lives in the weights


# ---------------------------------------------------------------- mining


def _obs(post_id: str, positive: bool, *attrs: Attr, weight: float = 1.0) -> Observation:
    return Observation(post_id=post_id, positive=positive, weight=weight, attrs=frozenset(attrs))


LISTICLE = Attr(DNARuleKind.STYLE, "style:listicle", "listicle")
ANALYTICAL = Attr(DNARuleKind.STYLE, "style:analytical", "analytical")
SUBSTACK = Attr(DNARuleKind.SOURCE, "substack", "Substack")


def _history() -> list[Observation]:
    """Skips every listicle, likes every analytical piece, all from the same source."""
    return [
        *(_obs(f"n{i}", False, LISTICLE, SUBSTACK) for i in range(3)),
        *(_obs(f"y{i}", True, ANALYTICAL, SUBSTACK) for i in range(3)),
    ]


def test_mining_finds_the_style_that_is_skipped_within_what_the_user_reads():
    mined = mine_rules(_history())
    assert [(r.kind, r.key) for r in mined.anti] == [(DNARuleKind.STYLE, "style:listicle")]
    assert [(r.kind, r.key) for r in mined.affinities] == [(DNARuleKind.STYLE, "style:analytical")]
    rule = mined.anti[0]
    assert rule.source == DNARuleSource.LEARNED
    assert 0 < rule.strength <= 1
    assert set(rule.evidence_ids) == {"n0", "n1", "n2"}


def test_mining_ignores_attributes_that_do_not_discriminate_or_lack_support():
    mined = mine_rules(_history())
    # Substack appears on every post: no lift either way.
    assert not any(r.key == "substack" for r in [*mined.anti, *mined.affinities])
    # Two skips is not a pattern.
    assert mine_rules(_history()[1:]).anti == []


def test_mining_respects_dismissed_rules():
    mined = mine_rules(_history(), dismissed=["style:style:listicle"])
    assert mined.anti == []


def test_confident_misses_outweigh_expected_ones_when_attributes_compete():
    """Same number of skips, but the listicle skips were confident misses and the
    long-read skips were on posts the user expected to dislike."""
    long_read = Attr(DNARuleKind.LENGTH, "long", "long reads")
    history = [
        *(_obs(f"c{i}", False, LISTICLE, weight=1.45) for i in range(3)),
        *(_obs(f"e{i}", False, long_read, weight=0.7) for i in range(3)),
        *(_obs(f"y{i}", True, ANALYTICAL) for i in range(6)),
    ]
    assert [r.key for r in mine_rules(history).anti] == ["style:listicle"]

    unweighted = [_obs(o.post_id, o.positive, *o.attrs, weight=1.0) for o in history]
    # Without confidence both look equally suspicious (or equally fine).
    assert len(mine_rules(unweighted).anti) in (0, 2)


def test_observations_dedupe_by_post_newest_wins_and_need_a_signal():
    snap = build_snapshot(_post("p1"), theme=None, matched_label=None, match_percent=95)
    docs = [
        {"post_id": "p1", "weight": -0.6, "snapshot": snap, "match_percent": 95},  # newest
        {"post_id": "p1", "weight": 0.7, "snapshot": snap},  # older reaction, superseded
        {"post_id": "p2", "weight": 0.0, "snapshot": snap},  # no signal
        {"post_id": "p3", "weight": 0.7},  # no snapshot
    ]
    obs = observations_from_interactions(docs)
    assert [(o.post_id, o.positive) for o in obs] == [("p1", False)]
    assert obs[0].weight == pytest.approx(1.45)  # banished a 95% match


def test_merge_keeps_chat_and_confirmed_rules_and_drops_stale_learned_ones():
    chat = DNARule(kind=DNARuleKind.TOPIC, key="custom:hype", source=DNARuleSource.CHAT)
    stale = DNARule(kind=DNARuleKind.LENGTH, key="long", source=DNARuleSource.LEARNED)
    confirmed = DNARule(
        kind=DNARuleKind.STYLE, key="style:listicle", source=DNARuleSource.CONFIRMED
    )
    dna = InterestDNA(anti=[chat, stale, confirmed], version=4)

    merged, proposals = merge_mined(dna, mine_rules(_history()))
    keys = {(r.kind, r.key, r.source) for r in merged.anti}
    assert (DNARuleKind.TOPIC, "custom:hype", DNARuleSource.CHAT) in keys
    assert (DNARuleKind.STYLE, "style:listicle", DNARuleSource.CONFIRMED) in keys  # not duplicated
    assert not any(k[1] == "long" for k in keys)  # stale learned rule dropped
    assert proposals == []  # listicle was already confirmed, so nothing new to ask
    assert merged.version == 5
    assert [r.key for r in merged.affinities] == ["style:analytical"]


def test_merge_is_a_noop_when_nothing_changed():
    first, proposals = merge_mined(InterestDNA(version=1), mine_rules(_history()))
    assert [r.key for r in proposals] == ["style:listicle"]
    again, new = merge_mined(first, mine_rules(_history()))
    assert again is first and new == []


def test_noticed_ranks_the_attribute_the_user_keeps_skipping_first():
    snap = build_snapshot(
        _post("p9", style="listicle", words=900), theme=None, matched_label=None, match_percent=None
    )
    chips = noticed_for(snap, _history())
    assert chips[0].key == "style:listicle"
    assert (chips[0].seen, chips[0].negative) == (3, 3)
    assert len(chips) <= 4
    assert (
        noticed_for(snap, _history(), dismissed=["style:style:listicle"])[0].key != "style:listicle"
    )


def test_noticed_with_no_history_still_offers_the_posts_own_attributes():
    snap = build_snapshot(
        _post("p1", style="listicle"), theme=None, matched_label=None, match_percent=None
    )
    chips = noticed_for(snap, [])
    assert chips and chips[0].kind == DNARuleKind.STYLE  # most actionable first
    assert all(c.seen == 0 for c in chips)


# ---------------------------------------------------------------- DNA arithmetic edge


def test_a_dislike_cannot_conjure_an_unknown_theme_into_the_dna():
    dna = InterestDNA(weights={"theme:space": 100.0}, version=2)
    assert adjust_weight(dna, "theme:markets", "Markets", -4.2) is dna
    assert adjust_weight(InterestDNA(), "theme:markets", "Markets", -4.2).weights == {}


# ---------------------------------------------------------------- service loop


class FakeUsers:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find_one(self, filt):
        doc = self.docs.get(filt["user_id"])
        return dict(doc) if doc else None

    def update_one(self, filt, update, upsert=False):
        self.docs[filt["user_id"]] = dict(update["$set"])


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, field, direction):
        self.docs = sorted(self.docs, key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)


class FakeInteractions:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, filt):
        out = [
            d
            for d in self.docs
            if d.get("user_id") == filt["user_id"] and d.get("snapshot") is not None
        ]
        return _Cursor(out)


def _service(posts: dict[str, dict]) -> tuple[UserProfileService, FakeUsers, FakeInteractions]:
    users, interactions = FakeUsers(), FakeInteractions()
    store = MagicMock()
    store.users, store.interactions = users, interactions
    store.get_by_id.side_effect = lambda pid: posts.get(pid)
    resolver = TagResolver(
        [
            Tag(
                id="theme:ai",
                kind=TagKind.THEME,
                label="AI",
                aliases=["artificial intelligence"],
            ),
            Tag(
                id="theme:space",
                kind=TagKind.THEME,
                label="Space",
                aliases=["space and astronomy"],
            ),
        ]
    )
    tags = MagicMock()
    tags.resolver.return_value = resolver
    service = UserProfileService(
        store=store,
        vectors=MagicMock(),
        engine=MagicMock(),
        client=MagicMock(),
        inference_client=MagicMock(),
        tag_service=tags,
    )
    return service, users, interactions


def _event(user: str, post_id: str, event: EventType, **kw: Any) -> Interaction:
    return Interaction(user_id=user, post_id=post_id, event=event, **kw)


def _seeded_service(posts):
    service, users, interactions = _service(posts)
    service.import_dna("u1", vector={"ai": 60, "space": 40}, prompt="p", excluded=[])
    return service, users, interactions


def test_banish_moves_the_theme_down_on_the_server_and_scales_with_confidence():
    posts = {"a": _post("a"), "b": _post("b")}
    service, users, interactions = _seeded_service(posts)
    start = service.get_dna("u1")
    ai0 = start.weights["theme:ai"]

    service.record_event_outcome(
        _event("u1", "a", EventType.NOT_INTERESTED, strength=2, match_percent=50)
    )
    after_neutral = service.get_dna("u1").weights["theme:ai"]
    assert after_neutral == pytest.approx(ai0 - 7.0, abs=0.2)

    service.record_event_outcome(
        _event("u1", "b", EventType.NOT_INTERESTED, strength=2, match_percent=100)
    )
    after_confident = service.get_dna("u1").weights["theme:ai"]
    assert after_neutral - after_confident > 7.0 * 1.3  # a confident miss costs more
    assert interactions.docs[-1]["snapshot"]["match_percent"] == 100
    assert users.docs["u1"]["dna"]["version"] > start.version


def test_resonate_raises_the_theme_and_passive_events_leave_the_dna_alone():
    posts = {
        "a": _post("a", canonical_tags=[{"id": "theme:space", "label": "Space", "kind": "theme"}])
    }
    service, _, interactions = _seeded_service(posts)
    before = service.get_dna("u1")

    service.record_event_outcome(_event("u1", "a", EventType.OPEN))
    service.record_event_outcome(_event("u1", "a", EventType.IMPRESSION, visible_ms=200))
    assert service.get_dna("u1").version == before.version
    assert all("snapshot" not in d for d in interactions.docs)

    service.record_event_outcome(_event("u1", "a", EventType.LIKE, strength=2))
    after = service.get_dna("u1")
    assert after.weights["theme:space"] == pytest.approx(
        before.weights["theme:space"] + 7.0, abs=0.2
    )


def test_resonate_is_a_toggle_second_click_undos_the_like():
    posts = {
        "a": _post("a", canonical_tags=[{"id": "theme:space", "label": "Space", "kind": "theme"}])
    }
    service, _, _ = _seeded_service(posts)
    before = service.get_dna("u1")

    service.record_event_outcome(_event("u1", "a", EventType.LIKE, strength=2, match_percent=50))
    liked = service.get_dna("u1")
    assert liked.weights["theme:space"] == pytest.approx(before.weights["theme:space"] + 7.0, abs=0.25)

    # Sending LIKE again for the same post should toggle it off and undo the DNA delta.
    service.record_event_outcome(_event("u1", "a", EventType.LIKE, strength=2, match_percent=50))
    unliked = service.get_dna("u1")
    assert unliked.weights["theme:space"] == pytest.approx(before.weights["theme:space"], abs=0.35)


def test_repeated_skips_of_one_style_surface_chips_then_a_proposal():
    posts = {f"n{i}": _post(f"n{i}", style="listicle") for i in range(3)}
    posts |= {f"y{i}": _post(f"y{i}", style="analytical") for i in range(3)}
    service, _, _ = _seeded_service(posts)

    for i in range(3):
        service.record_event_outcome(_event("u1", f"y{i}", EventType.LIKE, strength=2))
    first = service.record_event_outcome(_event("u1", "n0", EventType.NOT_INTERESTED, strength=2))
    assert first.proposals == []
    assert any(c.key == "style:listicle" for c in first.noticed)  # offered even on day one

    service.record_event_outcome(_event("u1", "n1", EventType.NOT_INTERESTED, strength=2))
    last = service.record_event_outcome(_event("u1", "n2", EventType.NOT_INTERESTED, strength=2))
    assert [(r.kind, r.key, r.source) for r in last.proposals] == [
        (DNARuleKind.STYLE, "style:listicle", DNARuleSource.LEARNED)
    ]
    dna = service.get_dna("u1")
    assert [r.key for r in dna.anti] == ["style:listicle"]
    assert [r.key for r in dna.affinities] == ["style:analytical"]


def test_dismissed_proposals_do_not_come_back():
    posts = {f"n{i}": _post(f"n{i}", style="listicle") for i in range(4)}
    posts |= {f"y{i}": _post(f"y{i}", style="analytical") for i in range(3)}
    service, _, _ = _seeded_service(posts)
    for i in range(3):
        service.record_event_outcome(_event("u1", f"y{i}", EventType.LIKE, strength=2))
    for i in range(3):
        service.record_event_outcome(_event("u1", f"n{i}", EventType.NOT_INTERESTED, strength=2))

    dna = service.get_dna("u1")
    service.patch_dna("u1", DNAPatch(base_version=dna.version, remove_anti=["style:listicle"]))
    outcome = service.record_event_outcome(_event("u1", "n3", EventType.NOT_INTERESTED, strength=2))
    assert outcome.proposals == []
    assert all(r.key != "style:listicle" for r in service.get_dna("u1").anti)


def test_post_theme_falls_back_to_resolving_category_then_custom():
    service, _, _ = _service({})
    assert service._post_theme(
        {"canonical_tags": [{"id": "theme:ai", "label": "AI", "kind": "theme"}]}
    ) == (
        "theme:ai",
        "AI",
    )
    assert service._post_theme({"metadata": {"category": "space"}}) == ("theme:space", "Space")
    assert service._post_theme({"facets": {"topics": ["Basket Weaving"]}}) == (
        "custom:basket-weaving",
        "Basket Weaving",
    )
    assert service._post_theme({}) is None


def test_dna_themes_become_retrieval_queries_weighted_by_share():
    service, _, _ = _seeded_service({})
    resolver = service.tags.resolver.return_value
    resolver._by_id["theme:ai"].embedding = [1.0, 0.0]
    resolver._by_id["theme:space"].embedding = [0.0, 1.0]

    profile = service.get_or_create("u1")
    vectors = service._dna_query_vectors(profile)
    assert {v.label for v in vectors} == {"AI", "Space"}
    assert sum(v.weight for v in vectors) == pytest.approx(0.25)
    ai = next(v for v in vectors if v.label == "AI")
    assert ai.weight > next(v for v in vectors if v.label == "Space").weight  # 60 vs 40

    # With nothing else known about the user, the DNA alone makes a usable query set.
    assert len(service.build_query_set(profile)) == 2


def test_one_like_does_not_drown_what_the_user_told_aura():
    service, users, _ = _seeded_service({})
    resolver = service.tags.resolver.return_value
    resolver._by_id["theme:ai"].embedding = [1.0, 0.0]
    resolver._by_id["theme:space"].embedding = [0.0, 1.0]
    profile = service.get_or_create("u1")
    profile.persona_vector = [0.5, 0.5]
    profile.state_vector = [0.0, 1.0]
    profile.positive_ids = ["p1"]

    vectors = service.build_query_set(profile).vectors
    behaviour = sum(v.weight for v in vectors if v.kind.value in {"state", "centroid"})
    assert behaviour == pytest.approx(0.08)
    assert sum(v.weight for v in vectors) == pytest.approx(1.0)

    profile.positive_ids = [f"p{i}" for i in range(20)]
    vectors = service.build_query_set(profile).vectors
    behaviour = sum(v.weight for v in vectors if v.kind.value in {"state", "centroid"})
    assert behaviour == pytest.approx(0.6)


def test_custom_dna_themes_still_steer_retrieval():
    service, _, _ = _service({})
    service.client.embed_query.return_value = [0.3, 0.7]
    profile = service.get_or_create("u1")
    key = "custom:basket-weaving"
    profile.dna = profile.dna.model_copy(
        update={"weights": {key: 100.0}, "labels": {key: "basket weaving"}}
    )

    vectors = service._dna_query_vectors(profile)
    assert [(v.label, v.vector) for v in vectors] == [("basket weaving", [0.3, 0.7])]
    service._dna_query_vectors(profile)
    service.client.embed_query.assert_called_once_with("basket weaving")
