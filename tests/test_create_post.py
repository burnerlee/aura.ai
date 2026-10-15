# Copyright (c) 2026 DevRev Inc. All rights reserved.

"""UGC create + hydrate (requires running MongoDB)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from scraper.api.app import create_app
from scraper.api.cards import UGC_SOURCE
from scraper.api.posts import CreatePostRequest, PostKind, create_user_post
from scraper.models.document import EmbeddingStatus
from scraper.query.engine import RecommendationEngine
from scraper.storage.mongodb import MongoDocumentStore

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_MONGO_TESTS") == "1",
    reason="SKIP_MONGO_TESTS=1",
)


@pytest.fixture
def store():
    s = MongoDocumentStore()
    if not s.ping():
        pytest.skip("MongoDB not available")
    yield s
    s.collection.delete_many({"source": UGC_SOURCE, "metadata.ugc": True})
    s.close()


def test_create_user_post_pending(store: MongoDocumentStore):
    raw, card = create_user_post(
        CreatePostRequest(
            kind=PostKind.SHORT,
            body="A quiet signal from the edge of the network tonight",
            category="cyberpunk",
            user_id="test-user-1",
        ),
        store=store,
    )
    assert str(raw["_id"]) == card.id
    assert card.source == UGC_SOURCE
    assert card.embedding_status == EmbeddingStatus.PENDING.value
    assert card.category == "cyberpunk"
    assert store.get_by_id(card.id) is not None


def test_create_and_get_via_api(store: MongoDocumentStore):
    engine = RecommendationEngine(store=store, vectors=MagicMock(), client=MagicMock())
    client = TestClient(create_app(engine=engine))

    with patch("scraper.api.app.embed_by_ids") as embed_mock:
        embed_mock.return_value = {"ready": 1, "processed": 1}
        response = client.post(
            "/posts",
            json={
                "kind": "article",
                "title": "Notes from the lab",
                "body": " ".join(["discovery"] * 20),
                "category": "ai",
                "user_id": "api-user",
                "wait_for_embed": False,
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    post_id = payload["post"]["id"]
    assert payload["post"]["embedding_status"] == "pending"
    embed_mock.assert_called()

    got = client.get(f"/posts/{post_id}")
    assert got.status_code == 200
    assert got.json()["id"] == post_id
    assert got.json()["title"] == "Notes from the lab"

    batch = client.get("/posts", params=[("ids", post_id)])
    assert batch.status_code == 200
    assert len(batch.json()) == 1


def test_embed_by_ids_with_mocks(store: MongoDocumentStore):
    from scraper.embedding.worker import embed_by_ids

    _, card = create_user_post(
        CreatePostRequest(
            kind=PostKind.SHORT,
            body="chrome and rain and late night radio signals",
            category="space",
            user_id="embed-user",
        ),
        store=store,
    )

    fake_vectors = MagicMock()
    fake_vectors.ensure_collection = MagicMock()
    fake_vectors.upsert_post = MagicMock(return_value="point-xyz")

    fake_gemini = MagicMock()
    fake_gemini.embed_document = MagicMock(return_value=[0.1] * 8)

    settings = store.settings.model_copy(update={"facets_enabled": False})
    summary = embed_by_ids(
        [card.id],
        store=store,
        vectors=fake_vectors,
        client=fake_gemini,
        settings=settings,
    )

    assert summary["ready"] == 1
    refreshed = store.get_by_id(card.id)
    assert refreshed["embedding_status"] == EmbeddingStatus.READY.value
    assert refreshed["embedding_id"] == "point-xyz"
