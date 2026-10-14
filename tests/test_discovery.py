# Copyright (c) 2026 DevRev Inc. All rights reserved.

from scraper.discovery.substack import SubstackDiscovery


def test_filter_categories_by_slug():
    discovery = SubstackDiscovery()
    cats = [
        {"id": 4, "slug": "technology", "name": "Technology", "leaderboard_enabled": True},
        {"id": 62, "slug": "business", "name": "Business", "leaderboard_enabled": True},
        {"id": "podcast", "slug": "podcast", "name": "Podcasts"},
        {"id": 1, "slug": "old", "name": "Old", "deprecated": True, "leaderboard_enabled": True},
    ]
    selected = discovery._filter_categories(
        cats, categories_filter=["technology", "business"], include_podcasts=True
    )
    assert {c["slug"] for c in selected} == {"technology", "business"}


def test_filter_skips_podcasts_when_disabled():
    discovery = SubstackDiscovery()
    cats = [
        {"id": 4, "slug": "technology", "name": "Technology", "leaderboard_enabled": True},
        {"id": "podcast", "slug": "podcast", "name": "Podcasts"},
    ]
    selected = discovery._filter_categories(cats, include_podcasts=False)
    assert [c["slug"] for c in selected] == ["technology"]


def test_to_target_is_blog_pointer_not_stored_doc():
    discovery = SubstackDiscovery()
    target = discovery._to_target(
        {
            "id": 99,
            "name": "Example",
            "subdomain": "example",
            "base_url": "https://example.substack.com",
            "author_name": "Ada",
        },
        category={"id": 4, "name": "Technology", "slug": "technology"},
        tier="rising",
        rank=1,
    )
    assert target.publication_id == "99"
    assert target.scrape_source_id == "example"
    assert target.category_slug == "technology"
    assert target.rank == 1
