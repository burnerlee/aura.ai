# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""Discover listing endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from scraper.api.app import create_app
from scraper.query.engine import RecommendationEngine


def test_discover_returns_cards():
    store = MagicMock()
    store.list_discover_diverse.return_value = [
        {
            "_id": "507f1f77bcf86cd799439011",
            "source": "substack",
            "external_id": "1",
            "title": "Hot take",
            "content_text": " ".join(["word"] * 50),
            "author": {"name": "Pat"},
            "reaction_count": 12,
            "embedding_status": "ready",
            "categories": ["ai"],
        }
    ]
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    client = TestClient(create_app(engine=engine))
    res = client.get("/discover", params={"k": 10})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["id"] == "507f1f77bcf86cd799439011"
    assert body[0]["title"] == "Hot take"
    store.list_discover_diverse.assert_called_once()


def test_discover_with_source_uses_single_source_query():
    store = MagicMock()
    store.list_discover.return_value = [
        {
            "_id": "507f1f77bcf86cd799439012",
            "source": "reddit",
            "external_id": "2",
            "title": "Thread",
            "content_text": " ".join(["word"] * 50),
            "author": {"name": "Pat"},
            "reaction_count": 0,
            "embedding_status": "ready",
            "categories": ["ai"],
        }
    ]
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    client = TestClient(create_app(engine=engine))
    res = client.get("/discover", params={"k": 10, "source": "reddit"})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["source"] == "reddit"
    store.list_discover.assert_called_once()
