# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Coarse themes over topic tags: LLM grouping, embedding fallback, resolver."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from scraper.models.tag import Tag, TagKind
from scraper.tags.themes import (
    MIN_THEMES,
    _Assignment,
    _AssignPlan,
    _ThemeGroup,
    _ThemePlan,
    build_themes,
    default_theme_count,
    group_topics_with_llm,
    themes_from_groups,
)
from scraper.tags.vocabulary import TagResolver, tag_refs_for_facets

# Two well-separated directions plus noise: "finance-ish" vs "health-ish" topics.
_RNG = np.random.default_rng(7)


def _vec(axis: int, dim: int = 8) -> list[float]:
    base = np.zeros(dim)
    base[axis] = 1.0
    return (base + _RNG.normal(0, 0.03, dim)).tolist()


def _topic(label: str, axis: int, docs: int = 1) -> Tag:
    slug = label.lower().replace(" ", "-")
    return Tag(
        id=f"topic:{slug}",
        kind=TagKind.TOPIC,
        label=label,
        doc_count=docs,
        embedding=_vec(axis),
    )


def _topics() -> list[Tag]:
    labels = {
        0: ["Stock Market", "Investing", "Federal Reserve", "Macroeconomics"],
        1: ["Public Health", "Epidemiology", "Neuroscience"],
        2: ["Pop Culture", "Celebrity Gossip", "Bing Crosby"],
        3: ["Software Engineering", "System Design", "Cloud Computing"],
        4: ["Career Advice", "Job Market", "Remote Work"],
        5: ["Geopolitics", "Elections", "American Politics"],
    }
    out: list[Tag] = []
    for axis, names in labels.items():
        for i, name in enumerate(names):
            out.append(_topic(name, axis, docs=10 - i))
    return out


def test_default_theme_count_scales_with_sqrt_and_clamps():
    assert default_theme_count(335) == 18
    assert default_theme_count(4) == 4  # never more themes than topics
    assert default_theme_count(10_000) == 24


def test_embedding_fallback_groups_by_direction_and_labels_by_top_member():
    topics = _topics()
    themes, parent_of = build_themes(topics, k=6)

    assert len(themes) == 6
    assert set(parent_of) == {t.id for t in topics}
    market_theme = parent_of["topic:stock-market"]
    assert parent_of["topic:investing"] == market_theme
    assert parent_of["topic:macroeconomics"] == market_theme
    assert parent_of["topic:public-health"] != market_theme
    theme = next(t for t in themes if t.id == market_theme)
    assert theme.label == "Stock Market"  # heaviest member names the theme
    assert "investing" in theme.aliases and "federal reserve" in theme.aliases
    assert theme.doc_count == sum(t.doc_count for t in topics if parent_of[t.id] == market_theme)
    assert abs(float(np.linalg.norm(theme.embedding)) - 1.0) < 1e-5


class FakeLLM:
    """Answers the theme-plan and assignment prompts from canned data."""

    def __init__(self, plan: _ThemePlan | None, assign: _AssignPlan | None = None) -> None:
        self.plan, self.assign, self.prompts = plan, assign or _AssignPlan(), []

    def generate_json(self, prompt: str, schema: type[BaseModel]):
        self.prompts.append(prompt)
        if schema is _ThemePlan:
            if self.plan is None:
                raise RuntimeError("boom")
            return self.plan
        return self.assign


def _plan() -> _ThemePlan:
    return _ThemePlan(
        themes=[
            _ThemeGroup(label="Markets & Investing", topics=["Stock Market", "investing"]),
            _ThemeGroup(label="Health", topics=["Public Health", "Epidemiology"]),
            _ThemeGroup(label="Culture", topics=["Pop Culture", "Bing Crosby", "Not A Real Tag"]),
        ]
    )


def test_llm_groups_are_matched_case_insensitively_and_unknown_labels_dropped():
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    assert groups is not None
    by_label = {label: [t.label for t in tags] for label, tags in groups}
    assert by_label["Markets & Investing"] == ["Stock Market", "Investing"]
    assert by_label["Culture"] == ["Pop Culture", "Bing Crosby"]


def test_llm_failure_or_degenerate_plan_returns_none():
    assert group_topics_with_llm(_topics(), FakeLLM(None)) is None
    two = _ThemePlan(themes=_plan().themes[:2])
    assert group_topics_with_llm(_topics(), FakeLLM(two)) is None
    assert group_topics_with_llm(_topics()[: MIN_THEMES - 1], FakeLLM(_plan())) is None


def test_llm_assigns_the_long_tail_in_a_second_pass(monkeypatch):
    monkeypatch.setattr("scraper.tags.themes.MAX_PROMPT_TOPICS", 6)
    llm = FakeLLM(
        _plan(),
        _AssignPlan(
            assignments=[
                _Assignment(topic="Federal Reserve", theme="markets & investing"),
                _Assignment(topic="Neuroscience", theme="Health"),
                _Assignment(topic="Elections", theme="Nonexistent Theme"),
            ]
        ),
    )
    groups = group_topics_with_llm(_topics(), llm)
    assert groups is not None
    by_label = {label: {t.label for t in tags} for label, tags in groups}
    assert "Federal Reserve" in by_label["Markets & Investing"]
    assert "Neuroscience" in by_label["Health"]
    assert all("Elections" not in members for members in by_label.values())
    assert len(llm.prompts) >= 2  # theme pass + at least one assignment chunk


def test_unassigned_topics_attach_to_nearest_theme_by_embedding():
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    assert groups is not None
    themes, parent_of = themes_from_groups(_topics(), groups)
    # Never in the LLM answer, but embedded near the finance direction.
    assert parent_of["topic:macroeconomics"] == parent_of["topic:stock-market"]
    assert parent_of["topic:celebrity-gossip"] == parent_of["topic:pop-culture"]
    assert set(parent_of) == {t.id for t in _topics()}
    assert len({t.id for t in themes}) == len(themes)


def test_theme_aliases_make_any_member_label_resolve_to_its_theme():
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    themes, parent_of = themes_from_groups(_topics(), groups)
    topics = _topics()
    for topic in topics:
        topic.parent_id = parent_of[topic.id]
    resolver = TagResolver([*topics, *themes], theme_threshold=0.75)

    markets = resolver.resolve("Federal Reserve", TagKind.THEME)
    assert markets is not None and markets.label == "Markets & Investing"
    assert resolver.resolve("federal-reserve", TagKind.THEME).id == markets.id


def test_theme_resolver_matches_through_the_nearest_topic_not_the_theme_centroid():
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    themes, parent_of = themes_from_groups(_topics(), groups)
    topics = _topics()
    for topic in topics:
        topic.parent_id = parent_of[topic.id]
    embeds = {
        "quant trading": _vec(0),  # close to the finance topics
        "quilting": _vec(7),  # close to nothing
    }
    resolver = TagResolver(
        [*topics, *themes], embed_fn=lambda text: embeds[text], theme_threshold=0.8
    )
    found = resolver.resolve("quant trading", TagKind.THEME)
    assert found is not None and found.id == parent_of["topic:stock-market"]
    assert resolver.resolve("quilting", TagKind.THEME) is None


def test_theme_resolver_never_matches_a_theme_centroid_directly():
    """A centroid of unrelated topics is vaguely near everything; only topics count."""
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    themes, _ = themes_from_groups(_topics(), groups)  # themes only: no topics supplied
    resolver = TagResolver(themes, embed_fn=lambda text: _vec(0), theme_threshold=0.0)
    assert resolver.resolve("anything at all", TagKind.THEME) is None


def test_post_refs_lead_with_the_primary_theme_and_dedupe_themes():
    groups = group_topics_with_llm(_topics(), FakeLLM(_plan()))
    themes, parent_of = themes_from_groups(_topics(), groups)
    topics = _topics()
    for topic in topics:
        topic.parent_id = parent_of[topic.id]
    resolver = TagResolver([*topics, *themes])

    refs = tag_refs_for_facets({"topics": ["Epidemiology", "Public Health", "Investing"]}, resolver)
    kinds = [r.kind for r in refs]
    assert kinds == [TagKind.THEME, TagKind.THEME, TagKind.TOPIC, TagKind.TOPIC, TagKind.TOPIC]
    assert [r.label for r in refs[:2]] == ["Health", "Markets & Investing"]
