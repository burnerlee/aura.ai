# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""FastAPI response-shape smoke tests (mocked engine / store)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from scraper.api.app import create_app
from scraper.models.user import UserProfile
from scraper.profile.service import EventOutcome
from scraper.query.engine import RecommendationEngine
from scraper.query.types import ScoredPost


def test_healthz_and_search_shape():
    store = MagicMock()
    store.get_many_by_ids.return_value = {}
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    engine.search = MagicMock(
        return_value=[
            ScoredPost(
                post_id="missing",
                score=0.8,
                payload={
                    "source": "substack",
                    "external_id": "1",
                    "title": "T",
                    "author_name": "A",
                },
                reason="because",
            )
        ]
    )
    client = TestClient(create_app(engine=engine))

    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/health").json() == {"status": "ok"}

    res = client.post("/search", json={"query": "climate", "k": 3, "explain": True})
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "missing"
    assert body[0]["why"] == "because"
    assert "body" in body[0]
    assert "embedding_status" in body[0]


def test_events_accept_like_mapping():
    store = MagicMock()
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    profiles = MagicMock()
    profiles.record_event_outcome.return_value = EventOutcome(
        profile=UserProfile(user_id="u1", persona_version=2)
    )
    client = TestClient(create_app(engine=engine, profiles=profiles))

    res = client.post(
        "/users/u1/events",
        json={"events": [{"post_id": "507f1f77bcf86cd799439011", "event": "like"}]},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["count"] == 1
    assert res.json()["persona_version"] == 2
    assert res.json()["noticed"] == [] and res.json()["proposals"] == []
    assert res.json()["dna"]["version"] == 0
    profiles.record_event_outcome.assert_called_once()


def test_create_post_queues_embed():
    store = MagicMock()
    raw = {
        "_id": "507f1f77bcf86cd799439011",
        "source": "aura",
        "external_id": "abc",
        "content_text": "neon rain on chrome streets tonight",
        "metadata": {"kind": "short", "category": "cyberpunk", "ugc": True},
        "author": {"name": "You"},
        "embedding_status": "pending",
        "categories": ["cyberpunk"],
        "tags": ["cyberpunk"],
    }
    store.upsert.return_value = raw
    store.ensure_indexes = MagicMock()
    store.get_by_id.return_value = raw
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())

    with patch("scraper.api.app.embed_by_ids") as embed_mock:
        client = TestClient(create_app(engine=engine))
        res = client.post(
            "/posts",
            json={
                "kind": "short",
                "body": "neon rain on chrome streets tonight",
                "category": "cyberpunk",
                "user_id": "u1",
            },
        )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["post"]["id"] == "507f1f77bcf86cd799439011"
    assert payload["post"]["category"] == "cyberpunk"
    embed_mock.assert_called()


def test_import_url_queues_embed():
    store = MagicMock()
    store.collection.find_one.return_value = None
    raw = {
        "_id": "507f1f77bcf86cd799439012",
        "source": "link",
        "external_id": "hash",
        "title": "Imported title",
        "content_text": " ".join(["hello"] * 60),
        "embedding_status": "pending",
        "url": "https://example.com/post",
        "canonical_url": "https://example.com/post",
        "embed_url": "https://example.com/post",
        "metadata": {"import_url": "https://example.com/post"},
    }
    store.upsert.return_value = raw
    store.ensure_indexes = MagicMock()
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())

    with patch("scraper.api.app.embed_by_ids") as embed_mock:
        with patch("scraper.api.app.import_document_from_url") as import_mock:
            import_mock.return_value = MagicMock()  # ContentDocument shape not required here
            client = TestClient(create_app(engine=engine))
            res = client.post("/imports/url", json={"url": "https://example.com/post"})

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["post"]["id"] == "507f1f77bcf86cd799439012"
    assert payload["post"]["source"] == "link"
    embed_mock.assert_called()


def test_import_url_dedupes_existing():
    store = MagicMock()
    existing = {
        "_id": "507f1f77bcf86cd799439013",
        "source": "substack",
        "external_id": "1",
        "title": "Existing",
        "content_text": " ".join(["word"] * 60),
        "embedding_status": "ready",
        "url": "https://a.substack.com/p/x",
        "canonical_url": "https://a.substack.com/p/x",
        "embed_url": "https://a.substack.com/embed/p/x",
    }
    store.collection.find_one.return_value = existing
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())

    with patch("scraper.api.app.embed_by_ids") as embed_mock:
        with patch("scraper.api.app.import_document_from_url") as import_mock:
            client = TestClient(create_app(engine=engine))
            res = client.post("/imports/url", json={"url": "https://a.substack.com/p/x"})

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["post"]["id"] == "507f1f77bcf86cd799439013"
    import_mock.assert_not_called()
    embed_mock.assert_not_called()


def test_live_search_discovers_and_imports():
    store = MagicMock()
    store.get_many_by_ids.return_value = {}
    store.ensure_indexes = MagicMock()
    store.settings = MagicMock()
    store.collection.find_one.return_value = None
    # Upsert returns a minimal Mongo doc shape.
    store.upsert.side_effect = [
        {
            "_id": "507f1f77bcf86cd799439020",
            "source": "link",
            "external_id": "hash-1",
            "title": "A",
            "content_text": "body",
            "embedding_status": "pending",
            "url": "https://example.com/a",
            "canonical_url": "https://example.com/a",
            "embed_url": "https://example.com/a",
            "metadata": {},
        }
    ]
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    engine.search = MagicMock(return_value=[])  # no embedded hits

    fake_item = MagicMock(
        title="A",
        google_link="https://news.google.com/rss/articles/abc",
        publisher_link="https://example.com/a",
        source="Example",
        published_at=None,
    )

    with patch("scraper.api.app.fetch_google_news_items") as fetch_mock:
        with patch("scraper.api.app.with_resolved_publishers") as resolve_mock:
            with patch("scraper.api.app.import_document_from_url") as import_mock:
                with patch("scraper.api.app.embed_by_ids") as embed_mock:
                    fetch_mock.return_value = ("https://news.google.com/rss/search?q=x", [fake_item])
                    resolve_mock.return_value = [fake_item]
                    import_mock.return_value = MagicMock()
                    client = TestClient(create_app(engine=engine))
                    res = client.post(
                        "/search/live",
                        json={"query": "latest news", "k": 5, "discover_k": 3, "wait_for_embed": False},
                    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert "results" in body and "imported" in body
    assert body["results"] == []
    assert len(body["imported"]) == 1
    embed_mock.assert_called()


def test_live_search_fast_path_skips_discovery():
    store = MagicMock()
    store.get_many_by_ids.return_value = {}
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    engine.search = MagicMock(return_value=[])
    # Hydrate will return whatever docs exist; we just want >=k so we skip discovery.
    # Simplest: mock hydrate_results itself by making engine.search return a ScoredPost
    # and store.get_many_by_ids return a doc for it.
    from scraper.query.types import ScoredPost

    engine.search = MagicMock(
        return_value=[ScoredPost(post_id="1", score=0.1, payload={"source": "link", "external_id": "e"})]
    )
    store.get_many_by_ids.return_value = {
        "1": {
            "_id": "1",
            "source": "link",
            "external_id": "e",
            "content_text": "x " * 50,
            "embedding_status": "ready",
        }
    }
    client = TestClient(create_app(engine=engine))
    with patch("scraper.api.app.fetch_google_news_items") as fetch_mock:
        res = client.post("/search/live", json={"query": "latest news", "k": 1})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert len(payload["results"]) == 1
    assert payload["imported"] == []
    fetch_mock.assert_not_called()
