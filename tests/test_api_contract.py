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
