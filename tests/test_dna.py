# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Server-side Interest DNA: build, seed, import, patch, reconcile, persist, HTTP."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from scraper.api.app import create_app
from scraper.models.tag import Tag, TagKind
from scraper.models.user import (
    DNAPatch,
    DNARule,
    DNARuleKind,
    DNARuleSource,
    InterestCentroid,
    InterestDNA,
    Persona,
    UserProfile,
)
from scraper.profile.aura import AuraProfileDraft
from scraper.profile.dna import (
    DNAVersionConflict,
    adjust_weight,
    apply_patch,
    build_dna_from_draft,
    confidence_scale,
    import_vector,
    normalize_weights,
    reconcile,
    seed_dna,
)
from scraper.profile.service import UserProfileService
from scraper.query.engine import RecommendationEngine
from scraper.tags.vocabulary import TagResolver


def _resolver() -> TagResolver:
    return TagResolver(
        [
            Tag(
                id="theme:practical-ai",
                kind=TagKind.THEME,
                label="Practical AI",
                aliases=["applied ai"],
                doc_count=10,
            ),
            Tag(
                id="theme:space",
                kind=TagKind.THEME,
                label="Space",
                aliases=["space and astronomy"],
                doc_count=4,
            ),
        ]
    )


def test_normalize_weights_sums_to_100_and_floors():
    out = normalize_weights({"a": 3, "b": 1, "c": 0})
    assert round(sum(out.values()), 1) == 100.0
    assert out["a"] > out["b"] > out["c"] >= 0
    assert normalize_weights({}) == {}


def test_normalize_weights_caps_keys_keeping_heaviest():
    raw = {f"k{i}": float(i + 1) for i in range(40)}
    out = normalize_weights(raw)
    assert len(out) == 24
    assert "k39" in out and "k0" not in out
    assert round(sum(out.values()), 1) == 100.0


def test_build_from_draft_maps_themes_to_tags_and_keeps_unknown_as_custom():
    draft = AuraProfileDraft(
        prompt="Practical AI and deep space, no hype.",
        themes=["practical-ai", "deep-space"],
        theme_weights={"practical-ai": 80, "deep-space": 40},
        anti_topics=["hype"],
    )
    dna = build_dna_from_draft(draft, _resolver())

    assert set(dna.weights) == {"theme:practical-ai", "custom:deep-space"}
    assert dna.weights["theme:practical-ai"] > dna.weights["custom:deep-space"]
    assert round(sum(dna.weights.values()), 1) == 100.0
    assert dna.labels["theme:practical-ai"] == "Practical AI"
    assert dna.labels["custom:deep-space"] == "deep space"
    assert [(r.kind, r.key, r.source) for r in dna.anti] == [
        (DNARuleKind.TOPIC, "custom:hype", DNARuleSource.CHAT)
    ]
    assert dna.version == 1
    assert dna.prompt.startswith("Practical AI")


def test_build_from_draft_resolves_aliases_and_merges_duplicates():
    draft = AuraProfileDraft(theme_weights={"Applied AI": 30, "practical ai": 30, "space": 40})
    dna = build_dna_from_draft(draft, _resolver())
    assert dna.weights == {"theme:practical-ai": 60.0, "theme:space": 40.0}


def test_build_from_draft_caps_a_theme_the_user_also_avoids():
    draft = AuraProfileDraft(theme_weights={"space": 50, "practical ai": 50}, anti_topics=["space"])
    dna = build_dna_from_draft(draft, _resolver())
    assert dna.weights["theme:space"] < 10
    assert dna.anti[0].key == "theme:space"


def test_build_without_resolver_still_produces_custom_keys():
    dna = build_dna_from_draft(AuraProfileDraft(themes=["indie games"]), None)
    assert list(dna.weights) == ["custom:indie-games"]
    assert dna.weights["custom:indie-games"] == 100.0


def test_themes_without_weights_get_a_small_share():
    draft = AuraProfileDraft(theme_weights={"practical ai": 90}, themes=["practical ai", "space"])
    dna = build_dna_from_draft(draft, _resolver())
    assert 0 < dna.weights["theme:space"] < dna.weights["theme:practical-ai"]


def test_rebuilding_replaces_chat_rules_but_keeps_learned_ones():
    previous = InterestDNA(
        weights={"theme:space": 100.0},
        anti=[
            DNARule(kind=DNARuleKind.TOPIC, key="custom:old", source=DNARuleSource.CHAT),
            DNARule(kind=DNARuleKind.STYLE, key="style:listicle", source=DNARuleSource.LEARNED),
        ],
        affinities=[DNARule(kind=DNARuleKind.STYLE, key="style:deep-dive")],
        version=3,
    )
    draft = AuraProfileDraft(theme_weights={"practical ai": 70}, anti_topics=["clickbait"])
    dna = build_dna_from_draft(draft, _resolver(), previous=previous)

    assert dna.version == 4
    assert {r.key for r in dna.anti} == {"custom:clickbait", "style:listicle"}
    assert [r.key for r in dna.affinities] == ["style:deep-dive"]


def test_empty_draft_keeps_previous_weights():
    previous = InterestDNA(
        weights={"theme:space": 100.0}, labels={"theme:space": "Space"}, version=2
    )
    dna = build_dna_from_draft(AuraProfileDraft(prompt="tweak"), _resolver(), previous=previous)
    assert dna.weights == {"theme:space": 100.0}
    assert dna.version == 3


def test_seed_from_persona_and_centroids():
    profile = UserProfile(
        user_id="u",
        persona=Persona(
            summary="Likes space.", topics=["space", "practical ai"], anti_topics=["crypto"]
        ),
        interest_centroids=[InterestCentroid(vector=[1.0], weight=0.5, label="Space")],
    )
    dna = seed_dna(profile, _resolver())
    assert dna is not None
    assert dna.version == 1
    assert set(dna.weights) == {"theme:space", "theme:practical-ai"}
    assert dna.anti[0].key == "custom:crypto"


def test_seed_ignores_placeholder_centroid_labels():
    profile = UserProfile(
        user_id="u",
        persona=Persona(topics=["space"]),
        interest_centroids=[
            InterestCentroid(vector=[1.0], weight=0.6, label="interest_0"),
            InterestCentroid(vector=[1.0], weight=0.4, label="interest_1"),
        ],
    )
    dna = seed_dna(profile, _resolver())
    assert dna is not None
    assert list(dna.weights) == ["theme:space"]
    only_placeholders = UserProfile(
        user_id="u",
        interest_centroids=[InterestCentroid(vector=[1.0], label="interest_0")],
    )
    assert seed_dna(only_placeholders, _resolver()) is None


def test_seed_returns_none_for_blank_profile():
    assert seed_dna(UserProfile(user_id="u"), _resolver()) is None


def test_import_maps_browser_seed_ids_and_excluded():
    dna = import_vector(
        {"ai": 40, "space": 30, "cyberpunk": 30},
        prompt="mine",
        excluded=["culture"],
        resolver=_resolver(),
    )
    assert dna is not None
    # Seed ids resolve through their descriptive hint ("space" -> "space and astronomy").
    assert dna.weights["theme:space"] == 30.0
    assert "custom:artificial-intelligence" in dna.weights
    assert "custom:cyberpunk" in dna.weights
    assert dna.prompt == "mine"
    assert dna.anti and dna.anti[0].kind == DNARuleKind.TOPIC
    assert import_vector({"ai": 0}, prompt="", excluded=[], resolver=None) is None


def _dna() -> InterestDNA:
    return InterestDNA(
        weights={"theme:space": 50.0, "theme:practical-ai": 30.0, "custom:games": 20.0},
        labels={
            "theme:space": "Space",
            "theme:practical-ai": "Practical AI",
            "custom:games": "games",
        },
        anti=[DNARule(kind=DNARuleKind.TOPIC, key="custom:hype")],
        version=5,
    )


def test_patch_set_weight_rescales_the_rest():
    out = apply_patch(_dna(), DNAPatch(base_version=5, set_weights={"theme:space": 70}))
    assert out.weights["theme:space"] == 70.0
    assert round(sum(out.weights.values()), 1) == 100.0
    # remaining 30 split 30:20 between the others
    assert out.weights["theme:practical-ai"] == 18.0
    assert out.weights["custom:games"] == 12.0
    assert out.version == 6


def test_patch_remove_weight_and_anti_and_add_confirmed_anti():
    patch = DNAPatch(
        base_version=5,
        remove_weights=["custom:games"],
        remove_anti=["custom:hype"],
        add_anti=[DNARule(kind=DNARuleKind.STYLE, key="style:listicle", label="listicle")],
    )
    out = apply_patch(_dna(), patch)
    assert "custom:games" not in out.weights and "custom:games" not in out.labels
    assert round(sum(out.weights.values()), 1) == 100.0
    assert [(r.key, r.source) for r in out.anti] == [("style:listicle", DNARuleSource.CONFIRMED)]


def test_patch_can_add_a_new_theme_with_derived_label():
    out = apply_patch(
        _dna(), DNAPatch(base_version=5, set_weights={"topic:cooking": 10}), resolver=_resolver()
    )
    assert out.weights["topic:cooking"] == 10.0
    assert out.labels["topic:cooking"] == "cooking"


def test_patch_with_stale_version_conflicts():
    with pytest.raises(DNAVersionConflict) as exc:
        apply_patch(_dna(), DNAPatch(base_version=4))
    assert exc.value.current_version == 5


def test_reconcile_follows_merged_themes_and_promotes_custom_ones():
    resolver = TagResolver(
        [
            Tag(id="theme:ai", kind=TagKind.THEME, label="AI", aliases=["games"]),
            Tag(id="theme:ml", kind=TagKind.THEME, label="ML", merged_into="theme:ai"),
        ]
    )
    dna = InterestDNA(
        weights={"theme:ml": 40.0, "theme:ai": 30.0, "custom:games": 30.0},
        labels={"theme:ml": "ML"},
        anti=[DNARule(kind=DNARuleKind.TOPIC, key="theme:ml")],
        version=2,
    )
    out, changed = reconcile(dna, resolver)
    assert changed
    assert out.weights == {"theme:ai": 100.0}
    assert out.anti[0].key == "theme:ai"
    assert out.version == 3

    again, changed_again = reconcile(out, resolver)
    assert not changed_again
    assert again.version == 3


def test_reconcile_lifts_legacy_topic_keys_to_their_parent_theme():
    resolver = TagResolver(
        [
            Tag(id="theme:markets", kind=TagKind.THEME, label="Markets & Investing"),
            Tag(
                id="topic:stock-market",
                kind=TagKind.TOPIC,
                label="Stock Market",
                parent_id="theme:markets",
            ),
            Tag(
                id="topic:investing",
                kind=TagKind.TOPIC,
                label="Investing",
                parent_id="theme:markets",
            ),
        ]
    )
    dna = InterestDNA(
        weights={"topic:stock-market": 60.0, "topic:investing": 40.0},
        anti=[
            DNARule(kind=DNARuleKind.TOPIC, key="topic:investing", source=DNARuleSource.LEARNED),
            DNARule(kind=DNARuleKind.STYLE, key="style:listicle"),
        ],
        version=1,
    )
    out, changed = reconcile(dna, resolver)
    assert changed
    assert out.weights == {"theme:markets": 100.0}
    assert out.labels["theme:markets"] == "Markets & Investing"
    # Fine-grained topic rules stay fine: a theme-level key would over-block.
    assert [r.key for r in out.anti] == ["topic:investing", "style:listicle"]


def test_adjust_weight_moves_one_theme_and_rescales_the_rest():
    dna = InterestDNA(
        weights={"theme:space": 50.0, "theme:practical-ai": 30.0, "custom:games": 20.0},
        labels={"theme:space": "Space"},
        version=3,
    )
    up = adjust_weight(dna, "theme:space", "Space", 7.0)
    assert up.weights["theme:space"] == 57.0
    assert round(sum(up.weights.values()), 1) == 100.0
    assert up.weights["theme:practical-ai"] / up.weights["custom:games"] == pytest.approx(
        1.5, rel=0.05
    )
    assert up.version == 4

    down = adjust_weight(dna, "theme:space", "Space", -100.0)
    assert down.weights["theme:space"] == 2.5  # floored, never erased

    capped = adjust_weight(dna, "theme:space", "Space", 100.0)
    assert capped.weights["theme:space"] == 80.0


def test_adjust_weight_introduces_an_unseen_theme_at_a_small_share():
    dna = InterestDNA(weights={"theme:space": 100.0}, version=1)
    out = adjust_weight(dna, "theme:cooking", "Cooking", 7.0)
    assert out.weights["theme:cooking"] == 15.0  # 8 starting share + 7
    assert out.labels["theme:cooking"] == "Cooking"
    assert round(sum(out.weights.values()), 1) == 100.0


def test_confidence_scale_amplifies_surprises():
    assert confidence_scale(False, None) == 1.0
    assert confidence_scale(False, 95) == pytest.approx(1.45)  # confident miss
    assert confidence_scale(False, 20) == pytest.approx(0.7)  # expected dud
    assert confidence_scale(True, 20) == pytest.approx(1.3)  # surprising like
    assert confidence_scale(True, 95) == pytest.approx(0.55)  # unsurprising like


# --- service persistence ----------------------------------------------------------


class FakeUsers:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find_one(self, filt: dict[str, Any]) -> dict[str, Any] | None:
        doc = self.docs.get(filt["user_id"])
        return dict(doc) if doc else None

    def update_one(
        self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> None:
        self.docs[filt["user_id"]] = dict(update["$set"])


def _service(resolver: TagResolver | None = None) -> tuple[UserProfileService, FakeUsers]:
    users = FakeUsers()
    store = MagicMock()
    store.users = users
    tags = MagicMock()
    tags.resolver.return_value = resolver or _resolver()
    tags.top_labels.return_value = ["Space"]
    client = MagicMock()
    client.embed_query.return_value = [0.1, 0.2, 0.3]
    service = UserProfileService(
        store=store,
        vectors=MagicMock(),
        engine=MagicMock(),
        client=client,
        inference_client=MagicMock(),
        tag_service=tags,
    )
    return service, users


def test_new_user_has_empty_unversioned_dna():
    service, _ = _service()
    dna = service.get_dna("u1")
    assert dna.version == 0 and dna.weights == {}


def test_legacy_profile_is_seeded_once_and_persisted():
    service, users = _service()
    legacy = UserProfile(user_id="u1", persona=Persona(summary="Space nerd.", topics=["space"]))
    users.docs["u1"] = {k: v for k, v in legacy.to_mongo().items() if k != "dna"}

    first = service.get_dna("u1")
    assert first.version == 1 and "theme:space" in first.weights
    assert users.docs["u1"]["dna"]["version"] == 1

    second = service.get_dna("u1")
    assert second.version == 1


def test_apply_aura_profile_persists_dna_with_persona():
    service, users = _service()
    draft = AuraProfileDraft(
        prompt="Space and practical AI.",
        topics=["space", "practical ai"],
        themes=["space", "practical ai"],
        theme_weights={"space": 60, "practical ai": 40},
    )
    profile = service.apply_aura_profile("u1", draft)

    assert profile.dna.weights == {"theme:space": 60.0, "theme:practical-ai": 40.0}
    assert users.docs["u1"]["dna"]["weights"]["theme:space"] == 60.0
    assert profile.persona.summary == "Space and practical AI."


def test_import_adopts_local_dna_once_and_never_overrides_server():
    service, _ = _service()
    dna, imported = service.import_dna(
        "u1", vector={"space": 70, "ai": 30}, prompt="local", excluded=[]
    )
    assert imported and dna.version == 1

    again, imported_again = service.import_dna("u1", vector={"space": 1}, prompt="x", excluded=[])
    assert not imported_again
    assert again.weights == dna.weights


def test_patch_dna_through_service_checks_version():
    service, _ = _service()
    service.import_dna("u1", vector={"space": 60, "ai": 40}, prompt="p", excluded=[])
    updated = service.patch_dna("u1", DNAPatch(base_version=1, set_weights={"theme:space": 80}))
    assert updated.version == 2 and updated.weights["theme:space"] == 80.0
    with pytest.raises(DNAVersionConflict):
        service.patch_dna("u1", DNAPatch(base_version=1))


def test_aura_chat_uses_vocabulary_when_client_sends_no_themes(monkeypatch):
    service, _ = _service()
    seen: dict[str, Any] = {}

    def fake_chat(messages, *, known_themes=None, **kwargs):
        seen["themes"] = known_themes
        raise RuntimeError("stop")

    monkeypatch.setattr("scraper.profile.service.chat_with_aura", fake_chat)
    monkeypatch.setattr("scraper.profile.service.get_chat_client", lambda settings: None)
    with pytest.raises(RuntimeError):
        service.aura_chat("u1", messages=[])
    assert seen["themes"] == ["Space"]


# --- HTTP -----------------------------------------------------------------------------


def _client(profiles: MagicMock, tags: MagicMock | None = None) -> TestClient:
    engine = RecommendationEngine(store=MagicMock(), vectors=MagicMock(), client=MagicMock())
    return TestClient(create_app(engine=engine, profiles=profiles, tags=tags or MagicMock()))


def test_get_and_patch_dna_endpoints():
    profiles = MagicMock()
    profiles.get_dna.return_value = InterestDNA(weights={"theme:space": 100.0}, version=1)
    profiles.patch_dna.return_value = InterestDNA(weights={"theme:space": 100.0}, version=2)
    client = _client(profiles)

    got = client.get("/users/u1/dna").json()
    assert got["weights"] == {"theme:space": 100.0} and got["version"] == 1

    res = client.patch(
        "/users/u1/dna", json={"base_version": 1, "set_weights": {"theme:space": 90}}
    )
    assert res.status_code == 200 and res.json()["version"] == 2
    sent: DNAPatch = profiles.patch_dna.call_args.args[1]
    assert sent.base_version == 1 and sent.set_weights == {"theme:space": 90}


def test_patch_dna_conflict_returns_409_with_current_version():
    profiles = MagicMock()
    profiles.patch_dna.side_effect = DNAVersionConflict(7)
    res = _client(profiles).patch("/users/u1/dna", json={"base_version": 1})
    assert res.status_code == 409
    assert res.json()["detail"]["current_version"] == 7


def test_import_dna_endpoint_reports_whether_it_imported():
    profiles = MagicMock()
    profiles.import_dna.return_value = (
        InterestDNA(weights={"theme:space": 100.0}, version=1),
        True,
    )
    res = _client(profiles).post(
        "/users/u1/dna/import",
        json={"vector": {"space": 100}, "prompt": "hi", "excluded_categories": ["culture"]},
    )
    body = res.json()
    assert body["imported"] is True and body["dna"]["version"] == 1
    kwargs = profiles.import_dna.call_args.kwargs
    assert kwargs == {"vector": {"space": 100}, "prompt": "hi", "excluded": ["culture"]}


def test_tags_endpoint_passes_filters():
    tags = MagicMock()
    tags.list_public.return_value = [{"id": "theme:space", "label": "Space", "doc_count": 3}]
    res = _client(MagicMock(), tags).get("/tags?kind=topic&limit=5&min_docs=2")
    assert res.status_code == 200
    assert res.json()[0]["id"] == "theme:space"
    tags.list_public.assert_called_once_with(kind=TagKind.TOPIC, limit=5, min_docs=2)


def test_profile_endpoint_includes_dna_and_hides_transcript():
    profiles = MagicMock()
    profile = UserProfile(user_id="u1", dna=InterestDNA(weights={"theme:space": 100.0}, version=1))
    profiles.get_or_create.return_value = profile
    profiles.ensure_dna.side_effect = lambda p: p
    body = _client(profiles).get("/users/u1/profile").json()
    assert body["dna"]["weights"] == {"theme:space": 100.0}
    assert "aura_conversation" not in body
